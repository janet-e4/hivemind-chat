#!/usr/bin/env python3
"""Verify generated ZHealth Knowledge visibility in a local Open WebUI instance.

This is an API-only diagnostic helper. It authenticates to Open WebUI, checks
the split ZHealth Knowledge bases that are visible to the caller, audits read
grants when the API exposes them, compares counts with the generated sync
manifest when available, and can optionally query one split vector collection.

No foundation-model API keys are configured or read by this script.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "http://localhost:3002/api/v1"
DEFAULT_MANIFEST = Path("/Volumes/Public/ZHealth/.hivemind/openwebui-corpus/openwebui-sync-manifest.json")
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

    def search_knowledge(self, query: str) -> tuple[list[dict[str, Any]], int]:
        items: list[dict[str, Any]] = []
        total = 0
        page = 1
        while True:
            params = urllib.parse.urlencode({"query": query, "page": page})
            res = self.request("GET", f"/knowledge/search?{params}")
            page_items = res.get("items", []) if isinstance(res, dict) else []
            total = res.get("total", len(items) + len(page_items)) if isinstance(res, dict) else len(page_items)
            items.extend(page_items)
            if len(items) >= total or not page_items:
                break
            page += 1
        return items, total

    def get_knowledge_files(
        self,
        knowledge_id: str,
        query: str | None = None,
        include_content: bool = False,
    ) -> dict[str, Any]:
        params: dict[str, str] = {"page": "1"}
        if query:
            params["query"] = query
        if include_content:
            params["include_content"] = "true"
        query_string = urllib.parse.urlencode(params)
        res = self.request("GET", f"/knowledge/{knowledge_id}/files?{query_string}")
        return res if isinstance(res, dict) else {"items": [], "total": 0}

    def query_collection(
        self,
        collection_name: str,
        query: str,
        k: int,
        hybrid: bool | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"collection_names": [collection_name], "query": query, "k": k}
        if hybrid is not None:
            body["hybrid"] = hybrid
        res = self.request("POST", "/retrieval/query/collection", body)
        return res if isinstance(res, dict) else {"raw": res}


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


def load_manifest(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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


def describe_grants(grants: list[dict[str, Any]] | None) -> list[str]:
    keys = [key for key in (grant_key(grant) for grant in grants or []) if key]
    return [
        f"{principal_type}:{principal_id}:{permission}"
        for principal_type, principal_id, permission in sorted(keys)
    ]


def has_public_read(grants: list[dict[str, Any]] | None) -> bool:
    return "user:*:read" in describe_grants(grants)


def has_user_read(grants: list[dict[str, Any]] | None, user_id: str) -> bool:
    return f"user:{user_id}:read" in describe_grants(grants)


def explicit_user_read_grants(grants: list[dict[str, Any]] | None) -> list[str]:
    keys = [key for key in (grant_key(grant) for grant in grants or []) if key]
    return [
        principal_id
        for principal_type, principal_id, permission in keys
        if principal_type == "user" and principal_id != "*" and permission == "read"
    ]


def manifest_expectations(manifest: dict[str, Any] | None) -> dict[str, Any]:
    if not manifest:
        return {"loaded": False}

    groups = manifest.get("groups") or []
    expected_by_name = {
        group["knowledge_name"]: {
            "key": group["key"],
            "knowledge_name": group["knowledge_name"],
            "file_count": len(group.get("manifest") or []),
        }
        for group in groups
        if isinstance(group, dict) and group.get("knowledge_name") and group.get("key")
    }
    expected_by_key = {item["key"]: item for item in expected_by_name.values()}
    return {
        "loaded": True,
        "source_root": manifest.get("source_root"),
        "output_root": manifest.get("output_root"),
        "group_count": len(expected_by_name),
        "file_count": manifest.get("file_count"),
        "expected_by_name": expected_by_name,
        "expected_by_key": expected_by_key,
    }


def resolve_collection(
    selector: str,
    matched: list[dict[str, Any]],
    expected: dict[str, Any],
) -> dict[str, Any] | None:
    by_id = {item.get("id"): item for item in matched if item.get("id")}
    if selector in by_id:
        return by_id[selector]

    by_name = {item.get("name"): item for item in matched if item.get("name")}
    if selector in by_name:
        return by_name[selector]

    expected_by_key = expected.get("expected_by_key") or {}
    expected_group = expected_by_key.get(selector)
    if expected_group:
        return by_name.get(expected_group["knowledge_name"])

    selector_lower = selector.lower()
    for item in matched:
        if str(item.get("name") or "").lower() == selector_lower:
            return item
    return None


def result_count_list(value: Any) -> int:
    if isinstance(value, list) and value and isinstance(value[0], list):
        return len(value[0])
    if isinstance(value, list):
        return len(value)
    return 0


def summarize_rag_result(result: dict[str, Any]) -> dict[str, Any]:
    documents = result.get("documents")
    metadatas = result.get("metadatas")
    distances = result.get("distances")

    first_document = None
    if isinstance(documents, list) and documents and isinstance(documents[0], list) and documents[0]:
        first_document = documents[0][0]
    elif isinstance(documents, list) and documents:
        first_document = documents[0]

    first_metadata = None
    if isinstance(metadatas, list) and metadatas and isinstance(metadatas[0], list) and metadatas[0]:
        first_metadata = metadatas[0][0]
    elif isinstance(metadatas, list) and metadatas:
        first_metadata = metadatas[0]

    return {
        "document_count": result_count_list(documents),
        "metadata_count": result_count_list(metadatas),
        "distance_count": result_count_list(distances),
        "first_document_preview": first_document[:240] if isinstance(first_document, str) else None,
        "first_metadata": first_metadata,
    }


def build_access_summary(
    items: list[dict[str, Any]],
    require_user_read: list[str],
) -> dict[str, Any]:
    visible_items = [item for item in items if isinstance(item.get("access_grants"), list)]
    missing_grants = [item.get("name") for item in items if "access_grants" not in item]
    public_read = [item.get("name") for item in visible_items if has_public_read(item.get("access_grants"))]
    missing_public_read = [
        item.get("name")
        for item in visible_items
        if not has_public_read(item.get("access_grants"))
    ]
    explicit_user_read_items = [
        item.get("name")
        for item in visible_items
        if explicit_user_read_grants(item.get("access_grants"))
    ]
    user_read: dict[str, list[str]] = {}
    missing_user_read: dict[str, list[str]] = {}
    for user_id in require_user_read:
        user_read[user_id] = [
            item.get("name")
            for item in visible_items
            if has_user_read(item.get("access_grants"), user_id)
        ]
        missing_user_read[user_id] = [
            item.get("name")
            for item in visible_items
            if not has_user_read(item.get("access_grants"), user_id)
        ]

    grant_counts = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "write_access": item.get("write_access"),
            "grants": describe_grants(item.get("access_grants")),
        }
        for item in visible_items
    ]
    return {
        "visible": len(visible_items),
        "not_visible": len(missing_grants),
        "not_visible_names": missing_grants,
        "public_read": len(public_read),
        "missing_public_read": missing_public_read,
        "explicit_user_read": len(explicit_user_read_items),
        "explicit_user_read_names": explicit_user_read_items,
        "user_read": {user_id: len(names) for user_id, names in user_read.items()},
        "missing_user_read": missing_user_read,
        "items": grant_counts,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--token")
    parser.add_argument("--email")
    parser.add_argument("--password")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--no-manifest", action="store_true")
    parser.add_argument("--knowledge-query", default="ZHealth")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--min-knowledge", type=int, default=1)
    parser.add_argument("--skip-file-counts", action="store_true")
    parser.add_argument("--require-manifest-match", action="store_true")
    parser.add_argument("--require-public-read", action="store_true")
    parser.add_argument(
        "--require-user-read",
        action="append",
        default=[],
        help="Require an explicit user:<id>:read grant on each visible ZHealth KB.",
    )
    parser.add_argument(
        "--collection",
        help="Optional split collection selector: manifest group key, exact Knowledge name, or Knowledge id.",
    )
    parser.add_argument("--collection-file-query", help="Optional filename/content query for /knowledge/{id}/files.")
    parser.add_argument("--include-content", action="store_true", help="Include file content in collection file query.")
    parser.add_argument("--rag-query", help="Optional retrieval query sent to /retrieval/query/collection.")
    parser.add_argument("--k", type=int, default=3, help="Top-k for --rag-query.")
    parser.add_argument("--no-hybrid", action="store_true", help="Force non-hybrid retrieval for --rag-query.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = None if args.no_manifest else load_manifest(args.manifest)
    expected = manifest_expectations(manifest)
    failures: list[str] = []

    client = OpenWebUIClient(args.base_url)
    ensure_token(client, args)

    search_items, api_total = client.search_knowledge(args.knowledge_query)
    matched = [item for item in search_items if str(item.get("name") or "").startswith(args.prefix)]

    if len(matched) < args.min_knowledge:
        failures.append(f"Only {len(matched)} ZHealth Knowledge bases matched prefix {args.prefix!r}.")

    expected_by_name = expected.get("expected_by_name") or {}
    matched_by_name = {item.get("name"): item for item in matched if item.get("name")}
    missing_from_api = sorted(set(expected_by_name) - set(matched_by_name)) if expected.get("loaded") else []
    extra_in_api = sorted(set(matched_by_name) - set(expected_by_name)) if expected.get("loaded") else []

    if args.require_manifest_match and missing_from_api:
        failures.append(f"{len(missing_from_api)} manifest Knowledge bases were not visible through the API.")

    file_count_sum = 0
    file_count_errors = []
    mismatched_file_counts = []
    if not args.skip_file_counts:
        for item in matched:
            name = item.get("name")
            try:
                files = client.get_knowledge_files(item["id"])
                count = int(files.get("total") or 0)
                file_count_sum += count
                expected_group = expected_by_name.get(name)
                if expected_group and count != expected_group["file_count"]:
                    mismatched_file_counts.append(
                        {
                            "name": name,
                            "actual": count,
                            "expected": expected_group["file_count"],
                        }
                    )
            except ApiError as e:
                file_count_errors.append({"name": name, "error": str(e)})
        if args.require_manifest_match and mismatched_file_counts:
            failures.append(f"{len(mismatched_file_counts)} visible Knowledge bases had file-count mismatches.")

    access = build_access_summary(matched, args.require_user_read)
    if (args.require_public_read or args.require_user_read) and access["not_visible"]:
        failures.append(f"{access['not_visible']} visible Knowledge bases did not expose access_grants.")
    if args.require_public_read and access["missing_public_read"]:
        failures.append(f"{len(access['missing_public_read'])} visible Knowledge bases are missing user:*:read.")
    for user_id, missing in access["missing_user_read"].items():
        if missing:
            failures.append(f"{len(missing)} visible Knowledge bases are missing user:{user_id}:read.")

    collection_probe = None
    if args.collection:
        selected = resolve_collection(args.collection, matched, expected)
        if not selected:
            failures.append(f"Could not resolve split collection selector: {args.collection}")
        else:
            collection_probe = {
                "selector": args.collection,
                "knowledge_id": selected.get("id"),
                "knowledge_name": selected.get("name"),
            }
            files = client.get_knowledge_files(
                selected["id"],
                query=args.collection_file_query,
                include_content=args.include_content,
            )
            collection_probe["files"] = {
                "query": args.collection_file_query,
                "total": files.get("total", 0),
                "sample_filenames": [
                    item.get("filename")
                    for item in (files.get("items") or [])[:5]
                    if isinstance(item, dict)
                ],
            }
            if args.rag_query:
                rag = client.query_collection(
                    selected["id"],
                    query=args.rag_query,
                    k=args.k,
                    hybrid=False if args.no_hybrid else None,
                )
                collection_probe["rag_query"] = {
                    "query": args.rag_query,
                    "k": args.k,
                    "hybrid": False if args.no_hybrid else "server-default",
                    "summary": summarize_rag_result(rag),
                }

    if expected.get("loaded") and args.require_manifest_match and file_count_sum != (expected.get("file_count") or 0):
        failures.append(
            f"Visible API file total {file_count_sum} did not match manifest file_count {expected.get('file_count')}."
        )

    output = {
        "ok": not failures,
        "base_url": args.base_url,
        "manifest": {
            "path": str(args.manifest) if not args.no_manifest else None,
            "loaded": expected.get("loaded", False),
            "source_root": expected.get("source_root"),
            "output_root": expected.get("output_root"),
            "expected_group_count": expected.get("group_count"),
            "expected_file_count": expected.get("file_count"),
        },
        "knowledge_search": {
            "query": args.knowledge_query,
            "prefix": args.prefix,
            "api_total_for_query": api_total,
            "matched_count": len(matched),
            "matched_file_count": file_count_sum if not args.skip_file_counts else None,
            "missing_from_api": missing_from_api,
            "extra_in_api": extra_in_api,
            "mismatched_file_counts": mismatched_file_counts,
            "file_count_errors": file_count_errors,
        },
        "access_grants": access,
        "collection_probe": collection_probe,
        "failures": failures,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ApiError as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)
