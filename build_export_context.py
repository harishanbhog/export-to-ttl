#!/usr/bin/env python3
"""Build ontology_export_context.json from hierarchy + global blocks + child-blocks API."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_profile(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    raw = load_json(path)
    return raw if isinstance(raw, dict) else None


def collect_floor_nodes(tree: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []

    def walk(node: dict[str, Any]) -> None:
        node_id = node.get("id")
        if node_id:
            nodes.append(node)
        for child in node.get("children", []) or []:
            if isinstance(child, dict):
                walk(child)

    for child in tree.get("children", []) or []:
        if isinstance(child, dict):
            walk(child)
    return nodes


def normalize_global_blocks(raw_blocks: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for block in raw_blocks.get("blocks", []) or []:
        if not isinstance(block, dict):
            continue
        bid = block.get("BID")
        if not bid:
            continue
        normalized.append(
            {
                "block_id": str(bid),
                "title": block.get("title", ""),
                "type": str(block.get("type", "")),
                "display_child_floors": str(block.get("display_child_floors", "0")),
                "default_block": str(block.get("default_block", "0")),
                "is_live_enabled": str(block.get("is_live_enabled", "0")),
                "analytics_enabled": str(block.get("analytics_enabled", "0")),
                "user_allowed_to_post": str(block.get("user_allowed_to_post", "0")),
            }
        )
    return normalized


def parse_childblocks_payload(payload: Any) -> dict[str, list[dict[str, Any]]]:
    """Normalize API payload into {floor_id: [block,..]} map.

    Supported shapes:
    - {"setspr_sdc_kan": {"floor_blocks": [...]}, ...}
    - [{"setspr_sdc_kan": {"floor_blocks": [...]}} , ...]
    - {"data": <any of the above>}
    """
    if isinstance(payload, dict) and "data" in payload:
        payload = payload.get("data")

    normalized: dict[str, list[dict[str, Any]]] = {}

    def normalize_blocks(items: Any) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for block in items or []:
            if not isinstance(block, dict):
                continue
            bid = block.get("block_id") or block.get("BID")
            if not bid:
                continue
            blocks.append(
                {
                    "block_id": str(bid),
                    "title": block.get("title", ""),
                    "type": str(block.get("type", "")),
                }
            )
        return blocks

    if isinstance(payload, dict):
        for floor_id, floor_obj in payload.items():
            if not isinstance(floor_id, str) or not isinstance(floor_obj, dict):
                continue
            normalized[floor_id] = normalize_blocks(floor_obj.get("floor_blocks", []))
        return normalized

    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            for floor_id, floor_obj in item.items():
                if not isinstance(floor_id, str) or not isinstance(floor_obj, dict):
                    continue
                normalized[floor_id] = normalize_blocks(floor_obj.get("floor_blocks", []))

    return normalized


def fetch_child_blocks_stub(base_url: str, token: str, hub_id: str, timeout: int = 15) -> dict[str, list[dict[str, Any]]]:
    """Fetch child-floor block map using the new API.

    API: GET /api/memory/floor/childblocks/{floor_id}

    For now this function behaves as a tolerant stub:
    - attempts real API call
    - if unavailable/unexpected, returns empty mapping
    """
    endpoint = f"{base_url.rstrip('/')}/api/memory/floor/childblocks/{hub_id}"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(endpoint, headers=headers, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        return parse_childblocks_payload(payload)
    except Exception:  # noqa: BLE001 - stub fallback by design
        return {}


def build_export_context(
    hierarchy: dict[str, Any],
    global_blocks_raw: dict[str, Any],
    profile: dict[str, Any] | None,
    base_url: str,
    token: str,
) -> tuple[dict[str, Any], int, int, int]:
    floor_nodes = collect_floor_nodes(hierarchy)
    global_blocks = normalize_global_blocks(global_blocks_raw)

    root_children = hierarchy.get("children", []) or []
    federation_id = ""
    if root_children and isinstance(root_children[0], dict):
        federation_id = str(root_children[0].get("id", ""))

    errors: list[dict[str, str]] = []
    child_block_map = fetch_child_blocks_stub(base_url=base_url, token=token, hub_id=federation_id)
    api_succeeded = 1 if child_block_map else 0
    api_failed = 0 if child_block_map else 1
    if not child_block_map:
        errors.append({"floor_id": federation_id or "unknown", "error": "childblocks API unavailable or empty; using no floor blocks"})

    floors: dict[str, dict[str, Any]] = {}
    for node in floor_nodes:
        floor_id = str(node.get("id"))
        floors[floor_id] = {
            "floor_id": floor_id,
            "floor_uid": str(node.get("FID", "")),
            "title": node.get("title") or node.get("name") or floor_id,
            "details": node.get("desc", ""),
            "floor_type": node.get("type", ""),
            "is_owner": "",
            "avatar": None,
            "app_id": None,
            "floor_blocks": child_block_map.get(floor_id, []),
            "source": "floor_childblocks_api",
        }

    profile_name = (profile or {}).get("profile_name", "")
    context = {
        "version": "v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "federation_id": federation_id,
        "category": profile_name,
        "profile_name": profile_name,
        "profile": profile or {},
        "hierarchy": hierarchy,
        "global_blocks": global_blocks,
        "floors": floors,
        "errors": errors,
    }
    return context, len(floor_nodes), api_succeeded, api_failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ontology export context from hierarchy + global blocks + childblocks API.")
    parser.add_argument("--hierarchy", required=True, help="Path to hierarchy JSON.")
    parser.add_argument("--global-blocks", required=True, help="Path to global blocks JSON.")
    parser.add_argument("--profile", required=False, help="Optional profile JSON path.")
    parser.add_argument("--base-url", required=True, help="xFloor base URL, e.g. https://appfloor.in")
    parser.add_argument("--token", required=True, help="Bearer token for childblocks API.")
    parser.add_argument("--out", required=True, help="Output context JSON path.")
    args = parser.parse_args()

    hierarchy = load_json(args.hierarchy)
    global_blocks_raw = load_json(args.global_blocks)
    profile = load_profile(args.profile)

    context, discovered, succeeded, failed = build_export_context(
        hierarchy=hierarchy,
        global_blocks_raw=global_blocks_raw,
        profile=profile,
        base_url=args.base_url,
        token=args.token,
    )

    Path(args.out).write_text(json.dumps(context, indent=2), encoding="utf-8")

    print(f"Floors discovered: {discovered}")
    print(f"Childblocks API succeeded: {succeeded}")
    print(f"Childblocks API failed: {failed}")
    print(f"Wrote context: {args.out}")


if __name__ == "__main__":
    main()
