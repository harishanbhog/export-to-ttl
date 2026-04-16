#!/usr/bin/env python3
"""Build ontology_export_context.json from hierarchy + global blocks + API child-block map."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://floortv.in/api/memory/"


def load_json(path: str) -> dict[str, Any]:
    """Load and parse a JSON file as a dictionary.

    Workflow note:
    - Used by CLI and SSE orchestration paths to ingest hierarchy/global payloads.
    - This function assumes top-level JSON object and lets exceptions bubble up
      so callers can decide how to report parsing errors.

    Example:
    >>> load_json("sample_hierarchy.json")
    {"children": [...]}  # simplified
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_profile(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    raw = load_json(path)
    return raw if isinstance(raw, dict) else None


def normalize_global_blocks(raw_blocks: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize raw global block payload to exporter-friendly shape.

    Workflow note:
    - Input often comes from legacy payload (`BID`, string flags).
    - Output guarantees `block_id` + known fields used by TTL serializer.
    - Unknown fields are intentionally ignored here to keep context compact.

    Example input:
    {"blocks": [{"BID": "101", "title": "Feeds", "display_child_floors": "1"}]}

    Example output:
    [{"block_id": "101", "title": "Feeds", "display_child_floors": "1", ...}]
    """
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


def fetch_child_blocks_stub(base_url: str, token: str, hub_id: str) -> dict[str, list[dict[str, Any]]]:
    """Return deterministic child-block data for offline/local workflows.

    Workflow note:
    - Stub mode is disabled in current flow.
    - Kept only as a reference fixture for developers.
    - Parameters are accepted for signature compatibility with future adapters.

    Example:
    >>> fetch_child_blocks_stub("", "", "setspr_sdc_kan")
    {"setspr_sdc_kan": [...], "setspr_sdc_kan_venkaborao": [...]}
    """
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




def fetch_child_blocks_api(floor_id: str, timeout: int = 15) -> dict[str, list[dict[str, Any]]]:
    """Real API handler for child blocks.

    API: <baseURL>/floor/child/blocks/{feeder_id}

    Supported response shapes:
    - {"list": [{"fed_path": "...", "blocks": [...]}, ...]}
    - {"data": {"list": [...]}}

    Workflow note:
    - `floor_id` is the feeder floor identifier provided by caller.
    - Function normalizes blocks and returns a map:
      `{ "<floor_id_from_api>": [<normalized blocks>] }`
    - If API returns an empty list, this returns `{}`.

    Example normalized return:
    {
      "setspr_sdc_kan": [{"block_id": "1776142091308", "title": "Feeds", ...}]
    }
    """
    try:
        import requests  # lazy import for runtime environments
    except ModuleNotFoundError as exc:
        raise RuntimeError("requests is required for child-block API mode") from exc

    api = resolve_api_settings()
    base_url = api["base_url"].rstrip("/") + "/"
    user_id = api["user_id"]
    app_id = api["app_id"]
    token = api["token"]
    token_present = bool(token)

    if not user_id or not app_id:
        raise RuntimeError("USER_ID and APP_ID must be set in .env or environment")

    endpoint = f"{base_url}floor/child/blocks/{floor_id}?user_id={user_id}&app_id={app_id}"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    print(
        "[childblocks-api] request params:",
        json.dumps(
            {
                "floor_id": floor_id,
                "base_url": base_url,
                "endpoint": endpoint,
                "user_id": user_id,
                "app_id": app_id,
                "token_present": token_present,
                "timeout": timeout,
            }
        ),
    )
    response = requests.get(endpoint, headers=headers, timeout=timeout)
    print("[childblocks-api] http status:", response.status_code)
    response.raise_for_status()
    payload = response.json()
    print("[childblocks-api] raw response:", json.dumps(payload)[:2000])

    if isinstance(payload, dict) and "data" in payload:
        payload = payload.get("data")

    normalized: dict[str, list[dict[str, Any]]] = {}

    def normalize_block(block: dict[str, Any]) -> dict[str, Any]:
        """Retain all block properties; ensure normalized block_id exists."""
        out = dict(block)
        bid = out.get("block_id") or out.get("BID")
        if bid is not None:
            out["block_id"] = str(bid)
        return out

    # Shape A: {"list": [{"fed_path":"...", "blocks":[...]}, ...]}
    if isinstance(payload, dict) and isinstance(payload.get("list"), list):
        print("[childblocks-api] response list count:", len(payload.get("list") or []))
        for item in payload["list"]:
            if not isinstance(item, dict):
                continue
            floor_id = item.get("fed_path")
            if not isinstance(floor_id, str) or not floor_id:
                continue
            blocks_raw = item.get("blocks", [])
            blocks: list[dict[str, Any]] = []
            for b in blocks_raw or []:
                if isinstance(b, dict):
                    nb = normalize_block(b)
                    if nb.get("block_id"):
                        blocks.append(nb)
            normalized[floor_id] = blocks
        print("[childblocks-api] normalized floor keys:", list(normalized.keys()))
        return normalized

    # Shape B/C intentionally not handled for now per API contract.
    print("[childblocks-api] unsupported response shape; normalized floor keys: []")
    return normalized


def resolve_child_block_map(feeder_id: str, use_api: bool) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, str]]]:
    """Resolve child blocks from API only and never raise to caller.

    Workflow note:
    - Stub mode is disabled by request.
    - This function always attempts live API.
    - On exception it returns empty map + error record (no stub fallback).
    - This function is the resilience boundary for context building.

    Example:
    >>> resolve_child_block_map("setspr_sdc_kan", use_api=False)
    ({}, [{"floor_id": "...", "error": "..."}])  # when API fails
    """
    if not use_api:
        print("[childblocks] stub mode disabled; forcing API call")

    try:
        child_map = fetch_child_blocks_api(floor_id=feeder_id)
        print("[childblocks] api map floor count:", len(child_map))
        return child_map, []
    except Exception as exc:  # noqa: BLE001
        print("[childblocks] api failure reason:", repr(exc))
        return {}, [
            {"floor_id": feeder_id or "unknown", "error": f"child blocks API failed; no stub fallback: {exc}"}
        ]



def collect_hierarchy_ids(hierarchy: dict[str, Any]) -> set[str]:
    """Collect all floor IDs from hierarchy tree.

    Workflow note:
    - Hierarchy is treated as source-of-truth.
    - Result is used to filter out any API floor keys that are unknown.

    Example:
    hierarchy children ids: A -> B -> C  => {"A", "B", "C"}
    """
    ids: set[str] = set()

    def walk(node: dict[str, Any]) -> None:
        node_id = node.get("id")
        if isinstance(node_id, str) and node_id:
            ids.add(node_id)
        for child in node.get("children", []) or []:
            if isinstance(child, dict):
                walk(child)

    for child in hierarchy.get("children", []) or []:
        if isinstance(child, dict):
            walk(child)
    return ids


def build_floors_from_api_map(
    child_block_map: dict[str, list[dict[str, Any]]],
    source_label: str,
    hierarchy_ids: set[str],
) -> tuple[dict[str, dict[str, Any]], int]:
    """Build floors section using only floors returned by API map.

    Per request, include only floors that actually appear in child-blocks response.
    Ignore any floor ids that are not present in hierarchy (hierarchy is source of truth).
    """
    floors: dict[str, dict[str, Any]] = {}
    for floor_id, blocks in child_block_map.items():
        if not isinstance(floor_id, str) or not floor_id:
            continue
        if floor_id not in hierarchy_ids:
            print(f"[childblocks] ignored non-hierarchy floor id from API: {floor_id}")
            continue
        if not blocks:
            continue
        floors[floor_id] = {
            "floor_blocks": blocks,
            "source": source_label,
        }
    return floors, len(floors)


def load_dotenv_values(dotenv_path: str = ".env") -> dict[str, str]:
    """Read simple KEY=VALUE pairs from .env without external deps."""
    path = Path(dotenv_path)
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_api_settings() -> dict[str, str]:
    """Resolve API settings from env/.env.

    Required from env/.env:
    - USER_ID (or XFLOOR_USER_ID)
    - APP_ID (or XFLOOR_APP_ID)

    Optional:
    - XFLOOR_TOKEN / TOKEN / BEARER_TOKEN
    - BASE_URL (defaults to https://floortv.in/api/memory/)
    """
    dotenv = load_dotenv_values()

    def pick(*keys: str, default: str = "") -> str:
        for key in keys:
            val = os.getenv(key) or dotenv.get(key)
            if val:
                return val.strip()
        return default

    return {
        "base_url": pick("BASE_URL", default=DEFAULT_BASE_URL),
        "token": pick("XFLOOR_TOKEN", "TOKEN", "BEARER_TOKEN"),
        "user_id": pick("USER_ID", "XFLOOR_USER_ID"),
        "app_id": pick("APP_ID", "XFLOOR_APP_ID"),
    }



def resolve_federation_id(hierarchy: dict[str, Any]) -> str:
    """Pick top meaningful federation floor id under root.

    If first child id looks like a root wrapper (e.g. root_*), prefer its first child id.

    Example:
    root_x -> setspr_sdc_kan -> ...  => returns "setspr_sdc_kan"
    """
    children = hierarchy.get("children", []) or []
    if not children or not isinstance(children[0], dict):
        return ""

    top = children[0]
    top_id = str(top.get("id", ""))
    if top_id and not top_id.startswith("root_"):
        return top_id

    grand = top.get("children", []) or []
    if grand and isinstance(grand[0], dict):
        return str(grand[0].get("id", ""))

    return top_id

def build_export_context(
    hierarchy: dict[str, Any],
    global_blocks_raw: dict[str, Any],
    profile: dict[str, Any] | None,
    use_api: bool,
    feeder_floor_id: str | None = None,
) -> tuple[dict[str, Any], int, int, int]:
    """Compose final export context consumed by TTL serializer.

    Workflow overview:
    1. Normalize global blocks.
    2. Resolve feeder floor id (`feeder_floor_id` override or hierarchy federation id).
    3. Fetch child-block map (API with resilience).
    4. Filter floors using hierarchy IDs.
    5. Assemble context envelope (`version`, `generated_at`, `profile`, `floors`, `errors`).

    Args:
    - hierarchy: full hierarchy JSON object.
    - global_blocks_raw: source blocks payload (expects `blocks` list).
    - profile: profile JSON (already fetched or optional).
    - use_api: whether to call live child-block API.
    - feeder_floor_id: optional override; useful for endpoint-style requests.

    Returns:
    - context dict
    - discovered floor count
    - API success count flag (0/1)
    - API failure count
    """
    global_blocks = normalize_global_blocks(global_blocks_raw)

    federation_id = feeder_floor_id or resolve_federation_id(hierarchy)

    child_block_map, errors = resolve_child_block_map(feeder_id=federation_id, use_api=use_api)
    source_label = "floor_childblocks_api"
    hierarchy_ids = collect_hierarchy_ids(hierarchy)
    floors, discovered = build_floors_from_api_map(child_block_map, source_label=source_label, hierarchy_ids=hierarchy_ids)

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
    print(f"[childblocks] mapped floors from provider: {len(child_block_map)}")
    if errors:
        print("[childblocks] errors:", json.dumps(errors))
    api_success = 1 if not errors else 0
    api_failed = len(errors)
    return context, discovered, api_success, api_failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ontology export context from hierarchy + global blocks using API childblocks map.")
    parser.add_argument("--hierarchy", required=True, help="Path to hierarchy JSON.")
    parser.add_argument("--global-blocks", required=True, help="Path to global blocks JSON.")
    parser.add_argument("--profile", required=False, help="Optional profile JSON path.")
    parser.add_argument("--out", required=True, help="Output context JSON path.")
    args = parser.parse_args()

    hierarchy = load_json(args.hierarchy)
    global_blocks_raw = load_json(args.global_blocks)
    profile = load_profile(args.profile)

    context, discovered, succeeded, failed = build_export_context(
        hierarchy=hierarchy,
        global_blocks_raw=global_blocks_raw,
        profile=profile,
        use_api=True,
    )

    Path(args.out).write_text(json.dumps(context, indent=2), encoding="utf-8")

    print(f"Floors discovered: {discovered}")
    print(f"Childblocks API succeeded: {succeeded} (api mode)")
    print(f"Childblocks API failed: {failed}")
    print(f"Wrote context: {args.out}")


if __name__ == "__main__":
    main()
