"""A minimal AES-CBC decryptor — just enough to read Moka's response envelope.

Moka wraps its public job-board API responses in AES-CBC + base64 and ships **both**
halves of the secret to every anonymous caller: the key arrives in the response itself
(`necromancer`) and the IV sits in plaintext in the page's `init-data`. So this is a
transport encoding, not an access control — there is nothing here to authenticate against
and nothing secret to recover. See `moka.py` for the full reasoning.

Implemented in pure Python on purpose: `openhire` installs via `pipx` and pulling a
compiled crypto wheel into the dependency set to undo one vendor's base64-with-extra-steps
is a bad trade. Correctness is pinned to the FIPS-197 vectors in `tests/test_moka.py`.

Decryption only — nothing in this project encrypts anything.
"""

from __future__ import annotations

# --- GF(2^8) helpers ----------------------------------------------------------
def _xtime(a: int) -> int:
    a <<= 1
    return (a ^ 0x1B) & 0xFF if a & 0x100 else a


def _mul(a: int, b: int) -> int:
    """Multiply in GF(2^8) modulo the AES polynomial."""
    out = 0
    while b:
        if b & 1:
            out ^= a
        a = _xtime(a)
        b >>= 1
    return out


def _build_sbox() -> tuple[list[int], list[int]]:
    """Derive the S-box from its definition rather than pasting a 256-byte table."""
    # Multiplicative inverses in GF(2^8), found by walking the generator-3 log table.
    inv = [0] * 256
    p = q = 1
    while True:
        p = p ^ _xtime(p)  # p *= 3
        q ^= q << 1
        q ^= q << 2
        q ^= q << 4
        q &= 0xFF
        if q & 0x80:
            q ^= 0x09  # q /= 3
        inv[p] = q
        if p == 1:
            break
    inv[0] = 0

    sbox = []
    for i in range(256):
        x = inv[i]
        # Affine transform: x ^ rotl(x,1) ^ rotl(x,2) ^ rotl(x,3) ^ rotl(x,4) ^ 0x63
        s = x
        for _ in range(4):
            x = ((x << 1) | (x >> 7)) & 0xFF
            s ^= x
        sbox.append(s ^ 0x63)

    rsbox = [0] * 256
    for i, s in enumerate(sbox):
        rsbox[s] = i
    return sbox, rsbox


_SBOX, _RSBOX = _build_sbox()
_RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36, 0x6C, 0xD8, 0xAB, 0x4D]


def _expand_key(key: bytes) -> list[list[int]]:
    """FIPS-197 key schedule → one 16-byte round key per round."""
    nk = len(key) // 4
    nr = nk + 6
    words = [list(key[4 * i : 4 * i + 4]) for i in range(nk)]
    for i in range(nk, 4 * (nr + 1)):
        t = list(words[i - 1])
        if i % nk == 0:
            t = t[1:] + t[:1]
            t = [_SBOX[b] for b in t]
            t[0] ^= _RCON[i // nk - 1]
        elif nk > 6 and i % nk == 4:
            t = [_SBOX[b] for b in t]
        words.append([a ^ b for a, b in zip(words[i - nk], t)])
    return [sum(words[4 * r : 4 * r + 4], []) for r in range(nr + 1)]


def _decrypt_block(block: bytes, round_keys: list[list[int]]) -> bytes:
    """AES inverse cipher on one 16-byte block. State is column-major, per FIPS-197."""
    nr = len(round_keys) - 1
    s = [b ^ k for b, k in zip(block, round_keys[nr])]

    for rnd in range(nr - 1, -1, -1):
        # InvShiftRows: row r rotates right by r (byte index = 4*col + row).
        shifted = [0] * 16
        for col in range(4):
            for row in range(4):
                shifted[4 * ((col + row) % 4) + row] = s[4 * col + row]
        # InvSubBytes
        s = [_RSBOX[b] for b in shifted]
        # AddRoundKey
        s = [b ^ k for b, k in zip(s, round_keys[rnd])]
        if rnd == 0:
            break
        # InvMixColumns
        mixed = [0] * 16
        for col in range(4):
            a = s[4 * col : 4 * col + 4]
            mixed[4 * col + 0] = _mul(a[0], 14) ^ _mul(a[1], 11) ^ _mul(a[2], 13) ^ _mul(a[3], 9)
            mixed[4 * col + 1] = _mul(a[0], 9) ^ _mul(a[1], 14) ^ _mul(a[2], 11) ^ _mul(a[3], 13)
            mixed[4 * col + 2] = _mul(a[0], 13) ^ _mul(a[1], 9) ^ _mul(a[2], 14) ^ _mul(a[3], 11)
            mixed[4 * col + 3] = _mul(a[0], 11) ^ _mul(a[1], 13) ^ _mul(a[2], 9) ^ _mul(a[3], 14)
        s = mixed

    return bytes(s)


def decrypt_cbc(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-CBC decrypt with PKCS#7 unpadding.

    Raises ValueError on anything malformed — callers treat that as a failed fetch
    rather than guessing at half-decoded output.
    """
    if len(key) not in (16, 24, 32):
        raise ValueError(f"bad AES key length: {len(key)}")
    if len(iv) != 16:
        raise ValueError(f"bad AES IV length: {len(iv)}")
    if not ciphertext or len(ciphertext) % 16:
        raise ValueError(f"ciphertext is not a whole number of blocks: {len(ciphertext)}")

    round_keys = _expand_key(key)
    out = bytearray()
    prev = iv
    for off in range(0, len(ciphertext), 16):
        block = ciphertext[off : off + 16]
        out.extend(a ^ b for a, b in zip(_decrypt_block(block, round_keys), prev))
        prev = block

    pad = out[-1]
    if not 1 <= pad <= 16 or bytes(out[-pad:]) != bytes([pad]) * pad:
        raise ValueError("bad PKCS#7 padding")
    return bytes(out[:-pad])
