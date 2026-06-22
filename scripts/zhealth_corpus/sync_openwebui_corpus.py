#!/usr/bin/env python3
"""Sync a generated ZHealth corpus manifest into Open WebUI knowledge bases.

Run build_openwebui_corpus.py first. This helper keeps each course/chapter as a
separate Open WebUI knowledge base, then preserves the generated
course/chapter/episode/topic directory tree inside that KB.

This uses the existing Open WebUI auth and knowledge/file APIs. It does not
configure foundation-model API keys.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://localhost:3002/api/v1"
DEFAULT_MANIFEST = Path("/Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json")


class ApiError(RuntimeError):
    pass


class OpenWebUIClient:
    def __init__(self, base_url: str, token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        body: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        data = None
        request_headers = dict(headers or {})
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request_headers.setdefault("Accept", "application/json")
        if self.token:
            request_headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(url, data=data, headers=request_headers, method=method)
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
        text = raw.decode("utf-8")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def signin(self, email: str, password: str) -> str:
        res = self.request("POST", "/auths/signin", {"email": email, "password": password})
        token = res.get("token") if isinstance(res, dict) else None
        if not token:
            raise ApiError("Signin succeeded but no token was returned.")
        self.token = token
        return token

    def get_knowledge_bases(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            res = self.request("GET", f"/knowledge/?page={page}")
            page_items = res.get("items", []) if isinstance(res, dict) else []
            items.extend(page_items)
            total = res.get("total", len(items)) if isinstance(res, dict) else len(items)
            if len(items) >= total or not page_items:
                break
            page += 1
        return items

    def create_knowledge(
        self,
        name: str,
        description: str,
        access_grants: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            "/knowledge/create",
            {"name": name, "description": description, "access_grants": access_grants or []},
        )

    def update_knowledge_access(
        self,
        knowledge_id: str,
        access_grants: list[dict[str, str]],
    ) -> dict[str, Any]:
        return self.request(
            "POST",
            f"/knowledge/{knowledge_id}/access/update",
            {"access_grants": access_grants},
        )

    def search_users(self, query: str, page: int = 1) -> dict[str, Any]:
        params = urllib.parse.urlencode({"query": query, "page": page})
        res = self.request("GET", f"/users/search?{params}")
        return res if isinstance(res, dict) else {"users": [], "total": 0}

    def sync_diff(self, knowledge_id: str, manifest: list[dict[str, Any]]) -> dict[str, Any]:
        compact = [
            {
                "filename": item["filename"],
                "path": item["path"],
                "checksum": item["checksum"],
                "size": item["size"],
            }
            for item in manifest
        ]
        return self.request("POST", f"/knowledge/{knowledge_id}/sync/diff", {"manifest": compact})

    def cleanup(self, knowledge_id: str, file_ids: list[str], dir_ids: list[str]) -> Any:
        return self.request(
            "POST",
            f"/knowledge/{knowledge_id}/sync/cleanup",
            {"file_ids": file_ids, "dir_ids": dir_ids},
        )

    def create_directory(self, knowledge_id: str, name: str, parent_id: str | None) -> dict[str, Any]:
        return self.request("POST", f"/knowledge/{knowledge_id}/dirs/create", {"name": name, "parent_id": parent_id})

    def upload_file(self, path: Path, metadata: dict[str, Any], process: bool = True) -> dict[str, Any]:
        boundary = "----hivemind-zhealth-sync"
        content_type = mimetypes.guess_type(path.name)[0] or "text/markdown"
        file_bytes = path.read_bytes()
        parts = []
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="metadata"\r\n\r\n'
                f"{json.dumps(metadata)}\r\n"
            ).encode("utf-8")
        )
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("utf-8")
        )
        parts.append(file_bytes)
        parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(parts)
        query = urllib.parse.urlencode(
            {
                "process": "true" if process else "false",
                "process_in_background": "false",
            }
        )
        req = urllib.request.Request(
            f"{self.base_url}/files/?{query}",
            data=body,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                return json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise ApiError(f"upload {path} failed: HTTP {e.code}: {detail}") from e

    def get_file(self, file_id: str) -> dict[str, Any]:
        return self.request("GET", f"/files/{file_id}")

    def wait_for_file_processed(self, file_id: str, timeout_sec: int = 180) -> dict[str, Any]:
        deadline = time.time() + timeout_sec
        last = {}
        while time.time() < deadline:
            last = self.get_file(file_id)
            status = (last.get("data") or {}).get("status")
            if status in {"completed", "failed"}:
                return last
            time.sleep(1)
        raise ApiError(f"Timed out waiting for file processing: {file_id}. Last status: {last}")


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def parse_user_email_grant(raw: str) -> tuple[str, str]:
    if ":" not in raw:
        raise SystemExit(
            f"Invalid --grant-user-email value: {raw!r}. Use EMAIL:read, EMAIL:write, or EMAIL:both."
        )
    email, permission = raw.rsplit(":", 1)
    email = email.strip().lower()
    permission = permission.strip().lower()
    if not email or "@" not in email:
        raise SystemExit(f"Invalid --grant-user-email email: {raw!r}.")
    if permission not in {"read", "write", "both"}:
        raise SystemExit(f"Invalid grant permission for {email}: {permission!r}. Use read, write, or both.")
    return email, permission


def grant_key(grant: dict[str, Any]) -> tuple[str, str, str] | None:
    principal_type = grant.get("principal_type")
    principal_id = grant.get("principal_id")
    permission = grant.get("permission")
    if principal_type not in {"user", "group"}:
        return None
    if permission not in {"read", "write"}:
        return None
    if not isinstance(principal_id, str) or not principal_id:
        return None
    return principal_type, principal_id, permission


def dedupe_grants(grants: list[dict[str, Any]]) -> list[dict[str, str]]:
    deduped: dict[tuple[str, str, str], dict[str, str]] = {}
    for grant in grants:
        key = grant_key(grant)
        if not key:
            continue
        principal_type, principal_id, permission = key
        deduped[key] = {
            "principal_type": principal_type,
            "principal_id": principal_id,
            "permission": permission,
        }
    return [deduped[key] for key in sorted(deduped)]


def describe_grants(grants: list[dict[str, Any]]) -> list[str]:
    keys = [key for key in (grant_key(grant) for grant in grants) if key]
    return [
        f"{principal_type}:{principal_id}:{permission}"
        for principal_type, principal_id, permission in sorted(keys)
    ]


def resolve_user_by_email(client: OpenWebUIClient, email: str) -> dict[str, Any]:
    result = client.search_users(email)
    matches = [
        user
        for user in result.get("users", [])
        if isinstance(user, dict) and str(user.get("email", "")).lower() == email.lower()
    ]
    if not matches:
        raise SystemExit(f"Open WebUI user not found for --grant-user-email: {email}")
    if len(matches) > 1:
        raise SystemExit(f"Open WebUI returned multiple exact users for email: {email}")
    user = matches[0]
    if not user.get("id"):
        raise SystemExit(f"Open WebUI user search returned no id for email: {email}")
    return user


def build_desired_access_grants(
    client: OpenWebUIClient,
    args: argparse.Namespace,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    grants: list[dict[str, str]] = []
    resolved_users: list[dict[str, str]] = []

    if args.public_read:
        grants.append({"principal_type": "user", "principal_id": "*", "permission": "read"})

    resolved_by_email: dict[str, dict[str, Any]] = {}
    for raw in args.grant_user_email or []:
        email, requested_permission = parse_user_email_grant(raw)
        user = resolved_by_email.get(email)
        if not user:
            user = resolve_user_by_email(client, email)
            resolved_by_email[email] = user
            resolved_users.append({"email": email, "user_id": user["id"]})

        permissions = ["read", "write"] if requested_permission == "both" else [requested_permission]
        for permission in permissions:
            grants.append({"principal_type": "user", "principal_id": user["id"], "permission": permission})

    return dedupe_grants(grants), resolved_users


def access_policy_requested(args: argparse.Namespace) -> bool:
    return bool(args.public_read or args.grant_user_email or args.clear_access_grants)


def access_audit(
    current_grants: list[dict[str, Any]],
    desired_grants: list[dict[str, str]] | None,
    replace: bool,
) -> dict[str, Any]:
    current_keys = set(describe_grants(current_grants))
    summary: dict[str, Any] = {
        "current": sorted(current_keys),
        "grant_count": len(current_keys),
    }
    if desired_grants is None:
        summary["ok"] = True
        return summary

    desired_keys = set(describe_grants(desired_grants))
    missing = sorted(desired_keys - current_keys)
    unexpected = sorted(current_keys - desired_keys)
    summary.update(
        {
            "expected": sorted(desired_keys),
            "missing": missing,
            "unexpected": unexpected,
            "ok": not missing and (not replace or not unexpected),
        }
    )
    return summary


def apply_access_policy(
    client: OpenWebUIClient,
    knowledge: dict[str, Any],
    desired_grants: list[dict[str, str]],
    replace: bool,
    dry_run: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    current_grants = knowledge.get("access_grants") or []
    before = access_audit(current_grants, desired_grants, replace=replace)

    next_grants = desired_grants if replace else dedupe_grants([*current_grants, *desired_grants])
    would_update = set(describe_grants(next_grants)) != set(describe_grants(current_grants))
    before["replace"] = replace
    before["would_update"] = would_update

    if dry_run or not would_update:
        return knowledge, before

    updated = client.update_knowledge_access(knowledge["id"], next_grants)
    after = access_audit(updated.get("access_grants") or [], desired_grants, replace=replace)
    target_keys = set(describe_grants(next_grants))
    after_keys = set(describe_grants(updated.get("access_grants") or []))
    dropped = sorted(target_keys - after_keys)
    after["replace"] = replace
    after["updated"] = True
    after["dropped"] = dropped
    if not after["ok"] or dropped:
        missing = ", ".join(after.get("missing") or [])
        unexpected = ", ".join(after.get("unexpected") or [])
        dropped_details = ", ".join(dropped)
        details = "; ".join(
            part
            for part in [
                f"missing: {missing}" if missing else "",
                f"unexpected: {unexpected}" if unexpected else "",
                f"dropped: {dropped_details}" if dropped_details else "",
            ]
            if part
        )
        raise ApiError(
            f"Access policy was not applied for {knowledge['name']} ({knowledge['id']}): {details}"
        )
    return updated, after


def find_or_create_kbs(
    client: OpenWebUIClient,
    groups: list[dict[str, Any]],
    create_missing: bool,
    dry_run: bool,
    create_access_grants: list[dict[str, str]] | None = None,
) -> dict[str, dict[str, Any]]:
    existing = {kb["name"]: kb for kb in client.get_knowledge_bases()}
    mapping = {}
    for group in groups:
        name = group["knowledge_name"]
        if name in existing:
            mapping[group["key"]] = existing[name]
            continue
        if dry_run:
            mapping[group["key"]] = {"id": "__missing__", "name": name, "missing": True}
            continue
        if not create_missing:
            raise SystemExit(f"Knowledge base missing: {name}. Re-run with --create-missing-kbs.")
        kb = client.create_knowledge(name, group["description"], create_access_grants)
        kb["created"] = True
        mapping[group["key"]] = kb
    return mapping


def ensure_directories(client: OpenWebUIClient, knowledge_id: str, diff: dict[str, Any]) -> dict[str, str]:
    directory_map = dict(diff.get("directory_map") or {})
    for directory_path in diff.get("mkdir") or []:
        parent_id = None
        current = []
        for part in directory_path.split("/"):
            current.append(part)
            current_path = "/".join(current)
            if current_path in directory_map:
                parent_id = directory_map[current_path]
                continue
            created = client.create_directory(knowledge_id, part, parent_id)
            directory_map[current_path] = created["id"]
            parent_id = created["id"]
    return directory_map


def sync_group(
    client: OpenWebUIClient,
    group: dict[str, Any],
    files_by_key: dict[tuple[str, str], dict[str, Any]],
    knowledge_id: str,
    dry_run: bool,
) -> dict[str, Any]:
    diff = client.sync_diff(knowledge_id, group["manifest"])
    changed = {(item["path"], item["filename"]) for item in diff.get("added", [])}
    changed.update((item["path"], item["filename"]) for item in diff.get("modified", []))

    summary = {
        "knowledge_name": group["knowledge_name"],
        "knowledge_id": knowledge_id,
        "added": len(diff.get("added", [])),
        "modified": len(diff.get("modified", [])),
        "deleted": len(diff.get("deleted", [])),
        "mkdir": len(diff.get("mkdir", [])),
        "rmdir": len(diff.get("rmdir", [])),
        "unmodified": diff.get("unmodified_count", 0),
    }
    if dry_run:
        return summary

    deleted_file_ids = [item["file_id"] for item in diff.get("deleted", []) if item.get("file_id")]
    if deleted_file_ids or diff.get("rmdir"):
        client.cleanup(knowledge_id, deleted_file_ids, diff.get("rmdir", []))

    directory_map = ensure_directories(client, knowledge_id, diff)
    stale_file_ids = [item["stale_file_id"] for item in diff.get("modified", []) if item.get("stale_file_id")]
    for key in sorted(changed):
        file_info = files_by_key[key]
        local_path = Path(file_info["local_path"])
        uploaded = client.upload_file(
            local_path,
            {
                "file_hash": file_info["checksum"],
                "knowledge_id": knowledge_id,
                "directory_id": directory_map.get(file_info["path"]),
                "zhealth": {
                    "course": file_info["course"],
                    "chapter": file_info["chapter"],
                    "episode": file_info["episode"],
                    "topic": file_info["topic"],
                    "topic_index": file_info["topic_index"],
                    "topic_count": file_info["topic_count"],
                    "source_transcript": file_info["source_transcript"],
                    "source_media": file_info.get("source_media"),
                },
            },
            process=True,
        )
        uploaded = client.wait_for_file_processed(uploaded["id"])
        status = (uploaded.get("data") or {}).get("status")
        if status == "failed":
            error = (uploaded.get("data") or {}).get("error") or "unknown processing error"
            raise ApiError(f"Processing failed for {local_path}: {error}")
    if stale_file_ids:
        client.cleanup(knowledge_id, stale_file_ids, [])
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token")
    parser.add_argument("--email")
    parser.add_argument("--password")
    parser.add_argument("--create-missing-kbs", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--group", action="append", help="Only sync group key, e.g. mindless-mobility/day01.")
    parser.add_argument(
        "--public-read",
        action="store_true",
        help="Ensure each targeted ZHealth knowledge base has user:* read access.",
    )
    parser.add_argument(
        "--grant-user-email",
        action="append",
        default=[],
        metavar="EMAIL:PERMISSION",
        help="Ensure access for an Open WebUI user email. PERMISSION is read, write, or both. Repeatable.",
    )
    parser.add_argument(
        "--replace-access-grants",
        action="store_true",
        help="Replace all existing grants with the requested policy instead of preserving extra grants.",
    )
    parser.add_argument(
        "--clear-access-grants",
        action="store_true",
        help="Explicitly clear all access grants on targeted knowledge bases.",
    )
    parser.add_argument(
        "--audit-access",
        action="store_true",
        help="Audit access grants for targeted knowledge bases and exit without syncing files or changing grants.",
    )
    parser.add_argument(
        "--repair-access",
        action="store_true",
        help="Apply the requested access policy and exit without syncing files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.clear_access_grants and (args.public_read or args.grant_user_email):
        raise SystemExit("--clear-access-grants cannot be combined with --public-read or --grant-user-email.")
    if args.clear_access_grants:
        args.replace_access_grants = True
    if args.repair_access and not access_policy_requested(args):
        raise SystemExit("Specify --public-read, --grant-user-email, or --clear-access-grants with --repair-access.")

    manifest = load_manifest(args.manifest)
    client = OpenWebUIClient(args.base_url)
    ensure_token(client, args)
    desired_grants: list[dict[str, str]] | None = None
    resolved_users: list[dict[str, str]] = []
    if access_policy_requested(args):
        desired_grants, resolved_users = build_desired_access_grants(client, args)

    groups = manifest["groups"]
    if args.group:
        wanted = set(args.group)
        groups = [group for group in groups if group["key"] in wanted]
        missing = wanted - {group["key"] for group in groups}
        if missing:
            raise SystemExit(f"Group key not found in manifest: {', '.join(sorted(missing))}")

    access_only = args.audit_access or args.repair_access
    kb_map = find_or_create_kbs(
        client,
        groups,
        create_missing=args.create_missing_kbs and not args.audit_access,
        dry_run=args.dry_run or args.audit_access or (args.repair_access and not args.create_missing_kbs),
        create_access_grants=desired_grants,
    )
    files_by_key = {(item["path"], item["filename"]): item for item in manifest["files"]}
    summaries = []
    for group in groups:
        knowledge = kb_map[group["key"]]
        knowledge_id = knowledge["id"]
        if knowledge_id == "__missing__":
            summaries.append(
                {
                    "knowledge_name": group["knowledge_name"],
                    "knowledge_id": None,
                    "missing": True,
                    "would_create": args.create_missing_kbs and not args.audit_access,
                    "file_count": len(group["manifest"]),
                }
            )
            continue

        created = bool(knowledge.get("created"))
        access_summary = None
        if args.audit_access:
            access_summary = access_audit(
                knowledge.get("access_grants") or [],
                desired_grants,
                replace=args.replace_access_grants,
            )
        elif desired_grants is not None:
            knowledge, access_summary = apply_access_policy(
                client,
                knowledge,
                desired_grants,
                replace=args.replace_access_grants,
                dry_run=args.dry_run,
            )

        if access_only:
            summaries.append(
                {
                    "knowledge_name": group["knowledge_name"],
                    "knowledge_id": knowledge_id,
                    "created": created,
                    "access_policy": access_summary,
                }
            )
            continue

        summary = sync_group(client, group, files_by_key, knowledge_id, dry_run=args.dry_run)
        summary["created"] = created
        if access_summary is not None:
            summary["access_policy"] = access_summary
        summaries.append(summary)

    print(
        json.dumps(
            {
                "dry_run": args.dry_run,
                "mode": "audit-access" if args.audit_access else "repair-access" if args.repair_access else "sync",
                "access_policy": (
                    {
                        "requested": describe_grants(desired_grants or []),
                        "replace": args.replace_access_grants,
                        "resolved_users": resolved_users,
                    }
                    if desired_grants is not None
                    else None
                ),
                "groups": summaries,
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
