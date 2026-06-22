#!/usr/bin/env python3
"""Audit or repair Open WebUI access grants for generated ZHealth knowledge.

The ZHealth sync creates ordinary Open WebUI knowledge bases. If those bases are
created by a service/admin account with no grants, normal users will not see
them in Workspace > Knowledge or chat attachment pickers.

This tool uses the Open WebUI API and does not configure foundation-model API
keys.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


DEFAULT_BASE_URL = "http://localhost:3002/api/v1"
DEFAULT_PREFIX = "ZHealth / "


class ApiError(RuntimeError):
    pass


class OpenWebUIClient:
    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, body: Any | None = None) -> Any:
        data = None
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                raw = res.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise ApiError(f"{method} {path} failed: HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise ApiError(f"{method} {path} failed: {e}") from e

        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def signin(self, email: str, password: str) -> str:
        res = self.request("POST", "/auths/signin", {"email": email, "password": password})
        token = res.get("token") if isinstance(res, dict) else None
        if not token:
            raise ApiError("Signin succeeded but no token was returned.")
        self.token = token
        return token

    def search_knowledge(self, query: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            params = urllib.parse.urlencode({"query": query, "page": page})
            res = self.request("GET", f"/knowledge/search?{params}")
            page_items = res.get("items", []) if isinstance(res, dict) else []
            items.extend(page_items)
            total = res.get("total", len(items)) if isinstance(res, dict) else len(items)
            if len(items) >= total or not page_items:
                break
            page += 1
        return items

    def update_access(self, knowledge_id: str, grants: list[dict[str, str]]) -> dict[str, Any]:
        return self.request("POST", f"/knowledge/{knowledge_id}/access/update", {"access_grants": grants})


def ensure_token(client: OpenWebUIClient, args: argparse.Namespace) -> None:
    if args.token:
        client.token = args.token
        return
    env_token = os.environ.get("OPENWEBUI_TOKEN")
    if env_token:
        client.token = env_token
        return

    email = args.email or os.environ.get("OPENWEBUI_EMAIL")
    password = args.password or os.environ.get("OPENWEBUI_PASSWORD")
    if not email or not password:
        raise SystemExit("Provide --token or OPENWEBUI_TOKEN, or provide --email/--password.")
    client.signin(email, password)


def normalize_grants(grants: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    normalized: dict[tuple[str, str, str], dict[str, str]] = {}
    for grant in grants or []:
        if not isinstance(grant, dict):
            continue
        principal_type = grant.get("principal_type")
        principal_id = grant.get("principal_id")
        permission = grant.get("permission")
        if principal_type not in {"user", "group"}:
            continue
        if permission not in {"read", "write"}:
            continue
        if not isinstance(principal_id, str) or not principal_id:
            continue
        normalized[(principal_type, principal_id, permission)] = {
            "principal_type": principal_type,
            "principal_id": principal_id,
            "permission": permission,
        }
    return list(normalized.values())


def grant_key(grant: dict[str, str]) -> tuple[str, str, str]:
    return (grant["principal_type"], grant["principal_id"], grant["permission"])


def parse_grant(value: str) -> dict[str, str]:
    try:
        principal_type, principal_id, permission = value.split(":", 2)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            "Grant must look like user:<id>:read, user:<id>:write, group:<id>:read, or group:<id>:write."
        ) from e
    grant = {"principal_type": principal_type, "principal_id": principal_id, "permission": permission}
    normalize_grants([grant])
    if not normalize_grants([grant]):
        raise argparse.ArgumentTypeError(f"Invalid grant: {value}")
    return grant


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token")
    parser.add_argument("--email")
    parser.add_argument("--password")
    parser.add_argument("--query", default="ZHealth")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--public-read", action="store_true", help="Ensure user:*:read on matching KBs.")
    parser.add_argument("--grant", action="append", type=parse_grant, default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    requested_grants = list(args.grant)
    if args.public_read:
        requested_grants.append({"principal_type": "user", "principal_id": "*", "permission": "read"})
    if not requested_grants:
        raise SystemExit("No repair requested. Pass --public-read and/or --grant.")

    client = OpenWebUIClient(args.base_url)
    ensure_token(client, args)

    items = [item for item in client.search_knowledge(args.query) if str(item.get("name") or "").startswith(args.prefix)]
    summaries = []
    updated = 0

    for item in items:
        existing = normalize_grants(item.get("access_grants"))
        merged = {grant_key(grant): grant for grant in existing}
        for grant in requested_grants:
            merged[grant_key(grant)] = grant
        new_grants = list(merged.values())
        changed = {grant_key(grant) for grant in new_grants} != {grant_key(grant) for grant in existing}

        summaries.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "changed": changed,
                "grant_count_before": len(existing),
                "grant_count_after": len(new_grants),
            }
        )
        if changed:
            updated += 1
            if not args.dry_run:
                client.update_access(item["id"], new_grants)

    print(
        json.dumps(
            {
                "dry_run": args.dry_run,
                "matched": len(items),
                "updated": updated,
                "items": summaries,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except ApiError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)
