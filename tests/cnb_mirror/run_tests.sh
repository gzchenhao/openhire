#!/usr/bin/env bash
# Logic test of the proposed snapshot-mirror stage against mock_cnb.py (local only).
set -u
# Usage: run_tests.sh [data-dir]. Reads the repository's own .cnb.yml and .cnb/web_trigger.yml.
T="$(cd "$(dirname "$0")" && pwd)"
P="$(cd "$T/../.." && pwd)"
D="${1:-$T/data}"; mkdir -p "$D"
PY="${PYTHON:-python3}"
"$PY" -I "$T/extract.py" "$P/.cnb.yml" "$P/.cnb/web_trigger.yml" "$D/stage.sh" "$D/env.json" || exit 1

# two different snapshots + a corrupt one
"$PY" -I - "$D" <<'PY'
import gzip, os, sqlite3, sys
d = sys.argv[1]
for tag, n in (("v1", 300), ("v2", 400)):
    db = os.path.join(d, f"{tag}.db")
    if os.path.exists(db): os.remove(db)
    c = sqlite3.connect(db)
    c.execute("create table jobs(id integer primary key, title text)")
    c.executemany("insert into jobs(title) values (?)", [(f"job {i} {tag}",) for i in range(n)])
    c.commit(); c.close()
    with open(db, "rb") as f, gzip.open(os.path.join(d, f"{tag}.db.gz"), "wb") as g:
        g.write(f.read())
raw = open(os.path.join(d, "v1.db.gz"), "rb").read()
open(os.path.join(d, "corrupt.db.gz"), "wb").write(raw[: len(raw) // 2])
open(os.path.join(d, "notsqlite.db.gz"), "wb").write(gzip.compress(b"hello world, definitely not sqlite " * 50))
PY

PORT="${CNB_MOCK_PORT:-18765}"
start_mock() { # $1 = gh file, $2 = mode
  cp "$1" "$D/current.gz"
  "$PY" -I "$T/mock_cnb.py" "$PORT" "$D/current.gz" "$D/state.json" ${2:-} &
  MOCK=$!
  for _ in $(seq 1 50); do curl -s -o /dev/null "http://127.0.0.1:$PORT/" && break; sleep 0.1; done
}
stop_mock() { kill "$MOCK" 2>/dev/null; wait "$MOCK" 2>/dev/null; }

run_stage() { # $1 = shell
  env -i PATH="$PATH" HOME="$HOME" no_proxy="127.0.0.1,localhost" NO_PROXY="127.0.0.1,localhost" \
    CNB_REPO_SLUG="${SLUG:-gzchenhao/openhire}" CNB_TOKEN=test-token \
    CNB_API_ENDPOINT="http://127.0.0.1:$PORT/" CNB_WEB_ENDPOINT="http://127.0.0.1:$PORT/web" \
    SNAPSHOT_SRC="http://127.0.0.1:$PORT/gh/openhire-index.db.gz" SNAPSHOT_TAG=snapshot \
    SNAPSHOT_NAME=openhire-index.db.gz SNAPSHOT_MIN_BYTES=100 \
    timeout 120 "$1" "$D/stage.sh"
}
check_state() { "$PY" -I -c '
import json,sys
s=json.load(open(sys.argv[1]))
rel=s["releases"].get("snapshot")
print("  errors:", s["errors"] or "none")
if rel:
    print("  release id", rel["id"], "| assets:", [(a["name"], a["size"]) for a in rel["assets"]])
    print("  body sha line:", [l for l in rel["body"].splitlines() if "sha256" in l])
' "$D/state.json"; }

pass=0; fail=0
expect() { # $1 = label, $2 = expected exit (0/nonzero), $3 = actual exit, $4 = grep pattern in output
  local ok=1
  if [ "$2" = 0 ] && [ "$3" != 0 ]; then ok=0; fi
  if [ "$2" != 0 ] && [ "$3" = 0 ]; then ok=0; fi
  if [ -n "${4:-}" ] && ! grep -q -- "$4" "$D/out.txt"; then ok=0; fi
  if [ $ok = 1 ]; then pass=$((pass+1)); echo "PASS: $1 (exit $3)"; else fail=$((fail+1)); echo "FAIL: $1 (exit $3)"; sed 's/^/    /' "$D/out.txt"; fi
}

for SH in dash bash; do
  command -v "$SH" >/dev/null 2>&1 || { echo "=== shell: $SH not installed, skipped"; continue; }
  echo "=== shell: $SH"
  rm -f "$D/state.json"
  start_mock "$D/v1.db.gz"
  run_stage $SH > "$D/out.txt" 2>&1; rc=$?
  expect "$SH first run creates release, uploads, verifies" 0 $rc "完成："
  check_state
  run_stage $SH > "$D/out.txt" 2>&1; rc=$?
  expect "$SH second run skips unchanged without downloading" 0 $rc "不用下载"
  cp "$D/v2.db.gz" "$D/current.gz"
  run_stage $SH > "$D/out.txt" 2>&1; rc=$?
  expect "$SH changed snapshot overwrites" 0 $rc "完成："
  check_state
  "$PY" -I -c '
import json,sys,hashlib
s=json.load(open(sys.argv[1])); rel=s["releases"]["snapshot"]
names=[a["name"] for a in rel["assets"]]
assert names.count("openhire-index.db.gz")==1 and names.count("openhire-index.db.gz.sha256")==1, names
sha=hashlib.sha256(open(sys.argv[2],"rb").read()).hexdigest()
assert ("sha256: "+sha) in rel["body"], "body sha mismatch"
assert not s["errors"], s["errors"]
print("  state OK: one copy of each asset, body has v2 sha, no protocol errors")
' "$D/state.json" "$D/v2.db.gz" && pass=$((pass+1)) || { fail=$((fail+1)); echo "FAIL: state check"; }
  cp "$D/corrupt.db.gz" "$D/current.gz"
  run_stage $SH > "$D/out.txt" 2>&1; rc=$?
  expect "$SH truncated gzip is rejected" 1 $rc "不是完整的 gzip"
  cp "$D/notsqlite.db.gz" "$D/current.gz"
  run_stage $SH > "$D/out.txt" 2>&1; rc=$?
  expect "$SH gzip that is not SQLite is rejected" 1 $rc "不是 SQLite"
  SLUG=someone/fork run_stage $SH > "$D/out.txt" 2>&1; rc=$?
  expect "$SH other repo is skipped" 0 $rc "跳过"
  stop_mock
  echo "--- relative verify_url mode"
  rm -f "$D/state.json"
  start_mock "$D/v1.db.gz" relative
  run_stage $SH > "$D/out.txt" 2>&1; rc=$?
  expect "$SH relative verify_url works" 0 $rc "完成："
  check_state
  stop_mock
done
echo "=== $pass passed, $fail failed"
