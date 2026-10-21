"""Local mock of the CNB release endpoints used by the snapshot-mirror stage, plus a fake
GitHub download URL. Only for exercising the shell logic; it models the documented
request shapes (api.cnb.cool swagger, as shipped in node-cnb / go-cnb), not CNB itself.

usage: python3 mock_cnb.py PORT GH_FILE STATE_JSON [relative]
"""
import json
import secrets
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1])
GH_FILE = sys.argv[2]
STATE_FILE = sys.argv[3]
RELATIVE_VERIFY = len(sys.argv) > 4 and sys.argv[4] == "relative"
REPO = "gzchenhao/openhire"
TOKEN = "test-token"
BASE = f"http://127.0.0.1:{PORT}"

lock = threading.Lock()
state = {"releases": {}, "next_id": 100, "pending": {}, "blobs": {}, "log": [], "errors": []}


def save():
    out = {k: v for k, v in state.items() if k not in ("blobs", "pending")}
    out["blob_sizes"] = {k: len(v) for k, v in state["blobs"].items()}
    with open(STATE_FILE, "w") as f:
        json.dump(out, f, indent=1)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj=None, raw=None, headers=None):
        body = raw if raw is not None else (json.dumps(obj).encode() if obj is not None else b"")
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        if obj is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _authed(self):
        ok = self.headers.get("Authorization") == f"Bearer {TOKEN}"
        acc = self.headers.get("Accept") == "application/vnd.cnb.api+json"
        if not ok:
            state["errors"].append(f"no/bad auth on {self.command} {self.path}")
        if not acc:
            state["errors"].append(f"bad Accept on {self.command} {self.path}")
        return ok

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _route(self):
        u = urllib.parse.urlsplit(self.path)
        return u.path, urllib.parse.parse_qs(u.query)

    def do_GET(self):
        path, q = self._route()
        with lock:
            state["log"].append(f"GET {self.path}")
            if path == "/gh/openhire-index.db.gz":
                data = open(GH_FILE, "rb").read()
                etag = '"' + __import__("hashlib").md5(data).hexdigest() + '"'
                state.setdefault("gh_full_downloads", 0)
                rng = self.headers.get("Range")
                if rng:
                    start, _, stop = rng.split("=")[1].partition("-")
                    start = int(start)
                    if start >= len(data):
                        return self._send(416, raw=b"")
                    part = data[start:int(stop) + 1] if stop else data[start:]
                    if not stop:
                        state["gh_full_downloads"] += 1
                    return self._send(206, raw=part, headers={"ETag": etag, "Content-Range": f"bytes {start}-{start+len(part)-1}/{len(data)}"})
                state["gh_full_downloads"] += 1
                return self._send(200, raw=data, headers={"ETag": etag})
            pre = f"/{REPO}/-/releases/tags/"
            if path.startswith(pre):
                tag = urllib.parse.unquote(path[len(pre):])
                if not self._authed():
                    return self._send(401, {"errcode": 401, "errmsg": "unauthorized"})
                rel = state["releases"].get(tag)
                return self._send(200, rel) if rel else self._send(404, {"errcode": 404, "errmsg": "not found"})
            pre = f"/web/{REPO}/-/releases/download/"
            if path.startswith(pre):
                if self.headers.get("Authorization"):
                    state["errors"].append("anonymous download carried a token")
                tag, name = path[len(pre):].split("/", 1)
                rel = state["releases"].get(tag)
                asset = next((a for a in (rel or {}).get("assets", []) if a["name"] == name), None)
                if not asset:
                    return self._send(404, {"errmsg": "no asset"})
                return self._send(302, raw=b"", headers={"Location": f"{BASE}/cosget/{asset['blob']}?sign=x"})
            if path.startswith("/cosget/"):
                if self.headers.get("Authorization"):
                    state["errors"].append("token forwarded to storage")
                return self._send(200, raw=state["blobs"][path[len("/cosget/"):]])
            return self._send(404, {"errmsg": "no route"})

    def do_POST(self):
        path, q = self._route()
        body = self._body()
        with lock:
            state["log"].append(f"POST {self.path}")
            if not self._authed():
                return self._send(401, {"errcode": 401, "errmsg": "unauthorized"})
            if path == f"/{REPO}/-/releases":
                f = json.loads(body)
                for k in ("tag_name", "target_commitish", "make_latest"):
                    if k not in f:
                        state["errors"].append(f"create release missing {k}")
                rid = str(state["next_id"]); state["next_id"] += 1
                rel = {"id": rid, "tag_name": f["tag_name"], "name": f.get("name", ""), "body": f.get("body", ""),
                       "draft": f.get("draft", False), "prerelease": f.get("prerelease", False), "assets": []}
                state["releases"][f["tag_name"]] = rel
                save()
                return self._send(201, rel)
            parts = path.strip("/").split("/")
            # gzchenhao/openhire/-/releases/{rid}/asset-upload-url
            if len(parts) == 6 and parts[5] == "asset-upload-url":
                rid = parts[4]
                f = json.loads(body)
                if f.get("overwrite") is not True or f.get("ttl") != 0 or not isinstance(f.get("size"), int):
                    state["errors"].append(f"bad upload-url form {f}")
                tok = secrets.token_hex(8)
                state["pending"][tok] = {"rid": rid, "name": f["asset_name"], "size": f["size"], "data": None}
                vpath = f"/{REPO}/-/releases/{rid}/asset-upload-confirmation/{tok}/" + urllib.parse.quote(f"releases/{rid}/{f['asset_name']}", safe="")
                save()
                return self._send(201, {"upload_url": f"{BASE}/cosput/{tok}?sign=y", "expires_in_sec": 3600,
                                        "verify_url": vpath if RELATIVE_VERIFY else BASE + vpath})
            if len(parts) >= 8 and parts[5] == "asset-upload-confirmation":
                tok = parts[6]
                p = state["pending"].pop(tok, None)
                if q.get("ttl") != ["0"]:
                    state["errors"].append(f"confirm without ttl=0: {self.path}")
                if not p or p["data"] is None:
                    return self._send(404, {"errmsg": "nothing uploaded"})
                if len(p["data"]) != p["size"]:
                    state["errors"].append("uploaded size differs from declared size")
                rel = next(r for r in state["releases"].values() if r["id"] == p["rid"])
                blob = secrets.token_hex(6)
                state["blobs"][blob] = p["data"]
                rel["assets"] = [a for a in rel["assets"] if a["name"] != p["name"]]
                rel["assets"].append({"id": blob, "name": p["name"], "size": len(p["data"]), "blob": blob,
                                      "browser_download_url": f"{BASE}/web/{REPO}/-/releases/download/{rel['tag_name']}/{p['name']}"})
                save()
                return self._send(200, {})
            return self._send(404, {"errmsg": "no route"})

    def do_PUT(self):
        path, q = self._route()
        body = self._body()
        with lock:
            state["log"].append(f"PUT {path}")
            if self.headers.get("Authorization"):
                state["errors"].append("token sent to storage PUT")
            tok = path[len("/cosput/"):]
            if tok not in state["pending"]:
                return self._send(403, raw=b"bad signature")
            state["pending"][tok]["data"] = body
            return self._send(200, raw=b"")

    def do_PATCH(self):
        path, q = self._route()
        body = self._body()
        with lock:
            state["log"].append(f"PATCH {path}")
            if not self._authed():
                return self._send(401, {"errcode": 401})
            rid = path.strip("/").split("/")[4]
            rel = next(r for r in state["releases"].values() if r["id"] == rid)
            rel.update({k: v for k, v in json.loads(body).items() if k in ("name", "body", "draft", "prerelease")})
            save()
            return self._send(200, {})


save()
ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
