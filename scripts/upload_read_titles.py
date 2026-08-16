#!/usr/bin/env python3
"""Upload scripts/read-titles.txt to a GitHub Gist for the cloud recommend.yml.

Enables the cloud path (半环 B 回流 → 云端 CI 出推荐).

Requires a GitHub Personal Access Token (PAT) with the "gist" scope. Provide it
via GITHUB_TOKEN env var (local machine, not committed). The gist id is stored in
a local state file (scripts/.gist-id) so subsequent runs update the same gist.

Usage:
    GITHUB_TOKEN=ghp_xxx GIST_DESC="fl read titles" python3 scripts/upload_read_titles.py

Creates the gist on first run; updates it (PATCH) on later runs.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


API = "https://api.github.com/gists"
DEFAULT_SOURCE = Path(__file__).resolve().parent / "read-titles.txt"
STATE_FILE = Path(__file__).resolve().parent / ".gist-id"


def request(method, url, token, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return exc.code, body


def main(argv=None) -> int:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("error: GITHUB_TOKEN 未设置", file=sys.stderr)
        return 2

    source = Path(argv[0]) if argv and argv[0] else DEFAULT_SOURCE
    if not source.exists():
        print(f"error: 找不到 read-titles.txt: {source}", file=sys.stderr)
        return 2
    content = source.read_text(encoding="utf-8")
    desc = os.environ.get("GIST_DESC", "fl paper read titles")

    # existing gist id from state file
    gist_id = ""
    if STATE_FILE.exists():
        gist_id = STATE_FILE.read_text(encoding="utf-8").strip()

    payload = {
        "description": desc,
        "public": False,
        "files": {"read-titles.txt": {"content": content}},
    }

    if gist_id:
        status, body = request("PATCH", f"{API}/{gist_id}", token, payload)
    else:
        status, body = request("POST", API, token, payload)

    if status not in (200, 201):
        print(f"error: gist upload HTTP {status}: {body}", file=sys.stderr)
        return 1

    new_id = str(body.get("id") or "")
    if new_id:
        STATE_FILE.write_text(new_id, encoding="utf-8")

    raw_url = "https://gist.githubusercontent.com/"
    # raw url 需要 gist id + 文件名，但 public=false 的 raw 需要知道 owner
    # 用 api 返回的 raw_url 更稳
    raw = ""
    for fname, fdata in (body.get("files") or {}).items():
        if fname == "read-titles.txt":
            raw = fdata.get("raw_url") or ""

    print(f"gist ok id={new_id}")
    if raw:
        print(f"RAW_URL={raw}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
