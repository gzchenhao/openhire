"""Export an employer's published job posts from Feishu Recruitment (飞书招聘) with the
employer's OWN app credentials, on the employer's own machine. Nothing else.

This is the second of the two hand-over options in the employer letter: the employer keeps
its app_id / app_secret, runs this file, and sends us the JSON it prints. The credentials
never leave their machine, which is the same logic as "your résumé never leaves yours".

What it calls (Feishu open platform, documented, read-only):
  POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal
  GET  https://open.feishu.cn/open-apis/hire/v1/websites                       (hire:site:readonly)
  GET  https://open.feishu.cn/open-apis/hire/v1/websites/{website_id}/job_posts (hire:site_job_post:readonly)
It never touches candidates, résumés, applications or offers; those scopes are not requested.

Usage (the employer):
  set FEISHU_APP_ID=cli_xxx
  set FEISHU_APP_SECRET=yyy
  python feishu_export.py > openhire-jobs.json

Standard library only, so it runs on any machine with Python 3.9+; no pip install.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://open.feishu.cn/open-apis"
PAGE_SIZE = 10  # the documented maximum for job_posts


def _post_json(url: str, body: dict, token: str | None = None) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, token: str, params: dict | None = None) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def tenant_token(app_id: str, app_secret: str) -> str:
    body = _post_json(f"{BASE}/auth/v3/tenant_access_token/internal", {"app_id": app_id, "app_secret": app_secret})
    if body.get("code") != 0:
        raise SystemExit(f"tenant_access_token failed: code={body.get('code')} msg={body.get('msg')}")
    return body["tenant_access_token"]


def list_websites(token: str) -> list[dict]:
    body = _get_json(f"{BASE}/hire/v1/websites", token, {"page_size": 20})
    if body.get("code") != 0:
        raise SystemExit(f"websites failed: code={body.get('code')} msg={body.get('msg')} "
                         "(is hire:site:readonly granted and the app published?)")
    return body.get("data", {}).get("website_list", []) or body.get("data", {}).get("items", [])


def list_job_posts(token: str, website_id: str) -> list[dict]:
    out: list[dict] = []
    page_token = None
    while True:
        body = _get_json(f"{BASE}/hire/v1/websites/{website_id}/job_posts", token,
                         {"page_size": PAGE_SIZE, "page_token": page_token})
        if body.get("code") != 0:
            raise SystemExit(f"job_posts failed for website {website_id}: code={body.get('code')} msg={body.get('msg')} "
                             "(is hire:site_job_post:readonly granted?)")
        data = body.get("data", {})
        out.extend(data.get("items", []))
        if not data.get("has_more"):
            return out
        page_token = data.get("page_token")
        time.sleep(0.1)  # well under the documented 50/s


def main() -> int:
    app_id = os.environ.get("FEISHU_APP_ID", "").strip()
    app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        print("Set FEISHU_APP_ID and FEISHU_APP_SECRET in the environment first.", file=sys.stderr)
        return 2
    token = tenant_token(app_id, app_secret)
    websites = list_websites(token)
    export = {"exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "websites": []}
    for site in websites:
        site_id = site.get("id") or site.get("website_id")
        posts = list_job_posts(token, site_id) if site_id else []
        export["websites"].append({"website": site, "job_posts": posts})
        print(f"website {site_id} ({site.get('name')}): {len(posts)} job posts", file=sys.stderr)
    json.dump(export, sys.stdout, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} from Feishu: {e.read().decode('utf-8', 'replace')[:300]}", file=sys.stderr)
        sys.exit(1)
