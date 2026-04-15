#!/usr/bin/env python3
"""Build ontology_export_context.json from hierarchy + global blocks + stubbed child-block map."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_profile(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    raw = load_json(path)
    return raw if isinstance(raw, dict) else None


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


def fetch_child_blocks_stub(_base_url: str, _token: str, _hub_id: str) -> dict[str, list[dict[str, Any]]]:
    """Stubbed child-blocks response. No API call is made in this MVP stage."""
    return {
        "setspr_sdc_kan": [
            {"block_id": "1776142091308", "title": "Feeds", "type": "1"},
            {"block_id": "kan_local_notice", "title": "Dept Circular", "type": "9"},
        ],
        "setspr_sdc_kan_venkaborao": [
            {"block_id": "1776142091308", "title": "Feeds", "type": "1"},
            {"block_id": "faculty_local_notes", "title": "My Notes", "type": "7"},
        ],
    }


def build_floors_from_hierarchy(
    hierarchy: dict[str, Any],
    child_block_map: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, dict[str, Any]], int]:
    floors: dict[str, dict[str, Any]] = {}
    discovered = 0

    def walk(node: dict[str, Any]) -> None:
        nonlocal discovered
        floor_id = node.get("id")
        if floor_id:
            floor_id_text = str(floor_id)
            discovered += 1
            floors[floor_id_text] = {
                "floor_id": floor_id_text,
                "floor_uid": str(node.get("FID", "")),
                "title": node.get("title") or node.get("name") or floor_id_text,
                "details": node.get("desc", ""),
                "floor_type": node.get("type", ""),
                "is_owner": "",
                "avatar": None,
                "app_id": None,
                "floor_blocks": child_block_map.get(floor_id_text, []),
                "source": "floor_childblocks_stub",
            }

        for child in node.get("children", []) or []:
            if isinstance(child, dict):
                walk(child)

    for child in hierarchy.get("children", []) or []:
        if isinstance(child, dict):
            walk(child)

    return floors, discovered


def build_export_context(
    hierarchy: dict[str, Any],
    global_blocks_raw: dict[str, Any],
    profile: dict[str, Any] | None,
    base_url: str,
    token: str,
) -> tuple[dict[str, Any], int, int, int]:
    global_blocks = normalize_global_blocks(global_blocks_raw)

    root_children = hierarchy.get("children", []) or []
    federation_id = ""
    if root_children and isinstance(root_children[0], dict):
        federation_id = str(root_children[0].get("id", ""))

    child_block_map = fetch_child_blocks_stub(base_url=base_url, token=token, hub_id=federation_id)
    floors, discovered = build_floors_from_hierarchy(hierarchy, child_block_map)

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
        "errors": [],
    }
    return context, discovered, 1, 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ontology export context from hierarchy + global blocks + stubbed childblocks map.")
    parser.add_argument("--hierarchy", required=True, help="Path to hierarchy JSON.")
    parser.add_argument("--global-blocks", required=True, help="Path to global blocks JSON.")
    parser.add_argument("--profile", required=False, help="Optional profile JSON path.")
    parser.add_argument("--base-url", required=True, help="Reserved for future real API mode.")
    parser.add_argument("--token", required=True, help="Reserved for future real API mode.")
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
    print(f"Childblocks API succeeded: {succeeded} (stub mode)")
    print(f"Childblocks API failed: {failed}")
    print(f"Wrote context: {args.out}")


if __name__ == "__main__":
    main()
