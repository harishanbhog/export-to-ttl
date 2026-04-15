#!/usr/bin/env python3
"""Build ontology_export_context.json from hierarchy + global blocks + floor info API."""

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


def fetch_floor_info(base_url: str, token: str, floor_id: str, timeout: int = 15) -> dict[str, Any]:
    endpoint = f"{base_url.rstrip('/')}/api/memory/floor/info/{floor_id}"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(endpoint, headers=headers, timeout=timeout)
    response.raise_for_status()
    payload = response.json()

    # tolerate both plain object and wrapped responses
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        raise ValueError("Unexpected API response shape")

    blocks: list[dict[str, Any]] = []
    for block in data.get("blocks", []) or []:
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

    return {
        "floor_id": str(data.get("floor_id") or floor_id),
        "floor_uid": str(data.get("floor_uid", "")),
        "title": data.get("title", ""),
        "details": data.get("details", ""),
        "floor_type": data.get("floor_type", ""),
        "is_owner": str(data.get("is_owner", "")),
        "avatar": data.get("avatar"),
        "app_id": data.get("app_id"),
        "floor_blocks": blocks,
        "source": "floor_info_api",
    }


def build_export_context(
    hierarchy: dict[str, Any],
    global_blocks_raw: dict[str, Any],
    profile: dict[str, Any] | None,
    base_url: str,
    token: str,
) -> tuple[dict[str, Any], int, int, int]:
    floor_nodes = collect_floor_nodes(hierarchy)
    global_blocks = normalize_global_blocks(global_blocks_raw)

    floors: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    success = 0
    failed = 0

    for node in floor_nodes:
        floor_id = str(node.get("id"))
        try:
            info = fetch_floor_info(base_url=base_url, token=token, floor_id=floor_id)
            floors[floor_id] = info
            success += 1
        except Exception as exc:  # noqa: BLE001 - continue on failures by design
            failed += 1
            errors.append({"floor_id": floor_id, "error": str(exc)})
            floors[floor_id] = {
                "floor_id": floor_id,
                "floor_uid": str(node.get("FID", "")),
                "title": node.get("title") or node.get("name") or floor_id,
                "details": node.get("desc", ""),
                "floor_type": node.get("type", ""),
                "is_owner": "",
                "avatar": None,
                "app_id": None,
                "floor_blocks": [],
                "source": "hierarchy_fallback",
            }

    root_children = hierarchy.get("children", []) or []
    federation_id = ""
    if root_children and isinstance(root_children[0], dict):
        federation_id = str(root_children[0].get("id", ""))

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
    return context, len(floor_nodes), success, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ontology export context from hierarchy + global blocks + floor API.")
    parser.add_argument("--hierarchy", required=True, help="Path to hierarchy JSON.")
    parser.add_argument("--global-blocks", required=True, help="Path to global blocks JSON.")
    parser.add_argument("--profile", required=False, help="Optional profile JSON path.")
    parser.add_argument("--base-url", required=True, help="xFloor base URL, e.g. https://appfloor.in")
    parser.add_argument("--token", required=True, help="Bearer token for floor info API.")
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
    print(f"API succeeded: {succeeded}")
    print(f"API failed: {failed}")
    print(f"Wrote context: {args.out}")


if __name__ == "__main__":
    main()
