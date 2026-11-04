#!/usr/bin/env python3
"""Push the current git-tracked files to a GitHub repo via the Git Data REST API.

Why this exists
---------------
In restricted networks the git transport (https://github.com:443) may be blocked
or forced through a proxy that returns 502, while the REST API
(https://api.github.com) stays reachable. This script reconstructs the push
entirely over API calls:

    blobs -> tree -> commit -> branch ref

It handles both an EMPTY repo (initial commit, no parents) and a NON-empty repo
(uses the existing branch tip as parent + base_tree, then fast-forwards).

Usage
-----
    # Windows (cmd):        set GH_TOKEN=ghp_xxx && python scripts/push_via_api.py --repo zcMia0/enterprise-rag-workbench
    # Windows (PowerShell): $env:GH_TOKEN="ghp_xxx"; python scripts/push_via_api.py --repo zcMia0/enterprise-rag-workbench
    # Git Bash / Linux:     GH_TOKEN=ghp_xxx python scripts/push_via_api.py --repo zcMia0/enterprise-rag-workbench

The token is read from the environment only, never written to disk.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"


def _request(method: str, url: str, token: str, payload: dict | None = None) -> tuple[int, dict]:
    """Perform one authenticated GitHub API request.

    Returns (http_status, parsed_json_or_error). Never raises on HTTP errors so
    callers can branch on status codes (e.g. 404 = branch missing).
    """
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"message": body}
        return exc.code, parsed


def _tracked_files(cwd: str) -> list[tuple[str, str]]:
    """Return [(path, mode)] for git-tracked files, respecting .gitignore."""
    raw = subprocess.check_output(["git", "ls-files", "-s", "-z"], cwd=cwd).decode("utf-8", "replace")
    entries: list[tuple[str, str]] = []
    for record in raw.split("\0"):
        if not record.strip():
            continue
        meta, path = record.split("\t", 1)
        mode = meta.split()[0]
        entries.append((path, "100755" if mode == "100755" else "100644"))
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="Push tracked files to GitHub via the REST API")
    parser.add_argument("--repo", required=True, help="owner/name, e.g. zcMia0/enterprise-rag-workbench")
    parser.add_argument("--branch", default="main", help="target branch (default: main)")
    parser.add_argument("--message", default="feat: 企业知识库 RAG Agent 工作台", help="commit message")
    parser.add_argument("--cwd", default=".", help="repo working directory")
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: 未设置 GH_TOKEN / GITHUB_TOKEN 环境变量", file=sys.stderr)
        return 2

    entries = _tracked_files(args.cwd)
    print(f"[PUSH] 待推送文件数: {len(entries)}  (branch={args.branch})")

    # 1) upload every file as a blob
    tree_entries: list[dict] = []
    for idx, (path, fmode) in enumerate(entries, 1):
        with open(os.path.join(args.cwd, path), "rb") as fh:
            content_b64 = base64.b64encode(fh.read()).decode("ascii")
        status, blob = _request(
            "POST", f"{API}/repos/{args.repo}/git/blobs", token,
            {"content": content_b64, "encoding": "base64"},
        )
        if status not in (200, 201):
            print(f"[PUSH] blob 失败 {path}: HTTP {status} {blob.get('message')}", file=sys.stderr)
            return 3
        tree_entries.append({"path": path, "mode": fmode, "type": "blob", "sha": blob["sha"]})
        print(f"[PUSH] blob {idx}/{len(entries)}: {path}")

    # 2) detect whether the branch already exists (empty vs non-empty repo)
    status, ref = _request("GET", f"{API}/repos/{args.repo}/git/ref/heads/{args.branch}", token)
    parents: list[str] = []
    tree_payload: dict = {"tree": tree_entries}
    if status == 200 and isinstance(ref, dict) and ref.get("object"):
        parent_sha = ref["object"]["sha"]
        parents = [parent_sha]
        _, parent_commit = _request("GET", f"{API}/repos/{args.repo}/git/commits/{parent_sha}", token)
        tree_payload["base_tree"] = parent_commit.get("tree", {}).get("sha")
        print(f"[PUSH] 非空仓库, 基于 {parent_sha[:8]} 追加提交")
    else:
        print("[PUSH] 空仓库, 创建初始提交")

    # 3) create tree
    status, tree = _request("POST", f"{API}/repos/{args.repo}/git/trees", token, tree_payload)
    if status not in (200, 201):
        print(f"[PUSH] tree 失败: HTTP {status} {tree.get('message')}", file=sys.stderr)
        return 4

    # 4) create commit
    status, commit = _request(
        "POST", f"{API}/repos/{args.repo}/git/commits", token,
        {"message": args.message, "tree": tree["sha"], "parents": parents},
    )
    if status not in (200, 201):
        print(f"[PUSH] commit 失败: HTTP {status} {commit.get('message')}", file=sys.stderr)
        return 5

    # 5) create or update the branch ref
    if parents:
        status, out = _request(
            "PATCH", f"{API}/repos/{args.repo}/git/refs/heads/{args.branch}", token,
            {"sha": commit["sha"], "force": True},
        )
    else:
        status, out = _request(
            "POST", f"{API}/repos/{args.repo}/git/refs", token,
            {"ref": f"refs/heads/{args.branch}", "sha": commit["sha"]},
        )
    if status not in (200, 201):
        print(f"[PUSH] ref 失败: HTTP {status} {out.get('message')}", file=sys.stderr)
        return 6

    print(f"[PUSH] 完成! commit={commit['sha']} branch={args.branch}")
    print(f"[PUSH] 仓库地址: https://github.com/{args.repo}")
    print(f"[PUSH] 提交详情: https://github.com/{args.repo}/commit/{commit['sha']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
