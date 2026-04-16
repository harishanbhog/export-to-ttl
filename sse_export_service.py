#!/usr/bin/env python3
"""SSE-style orchestration for one-call context build + TTL export.

This module is written to mirror a FastAPI endpoint workflow:
1) receive floor_id, profile_name, and payload JSON
2) fetch floor child blocks via existing API flow
3) fetch profile from Redis (stubbed)
4) build context + export Turtle
5) stream progress events (SSE formatted lines)
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from build_export_context import build_export_context, load_json
from export_ttl import serialize_context_to_ttl


@dataclass
class ExportRequest:
    floor_id: str
    profile_name: str
    payload: dict[str, Any]
    use_api: bool = True


def sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def fetch_profile_from_redis_stub(profile_name: str) -> dict[str, Any]:
    """Stub for profile lookup from Redis.

    Replace with real Redis lookup in integration layer.
    """
    bundled = Path("sample_profile.json")
    if bundled.exists():
        profile = json.loads(bundled.read_text(encoding="utf-8"))
        if isinstance(profile, dict):
            profile = dict(profile)
            profile["profile_name"] = profile_name
            return profile
    return {
        "profile_name": profile_name,
        "namespace_prefix": "",
        "namespace_uri": "",
        "declare_classes": [],
        "floor_category_map": {},
        "block_title_map": {},
    }


def stream_ttl_export(request: ExportRequest) -> Iterator[str]:
    payload = request.payload if isinstance(request.payload, dict) else {}
    hierarchy = payload.get("hierarchy")
    global_blocks = payload.get("global_blocks")

    if not isinstance(hierarchy, dict):
        yield sse_event("error", {"message": "payload.hierarchy must be a JSON object"})
        return
    if not isinstance(global_blocks, dict):
        yield sse_event("error", {"message": "payload.global_blocks must be a JSON object"})
        return

    yield sse_event("progress", {"stage": "profile_lookup", "status": "started"})
    profile = fetch_profile_from_redis_stub(request.profile_name)
    yield sse_event("progress", {"stage": "profile_lookup", "status": "completed"})

    yield sse_event(
        "progress",
        {"stage": "context_build", "status": "started", "floor_id": request.floor_id, "use_api": request.use_api},
    )
    context, floors_discovered, api_success, api_failed = build_export_context(
        hierarchy=hierarchy,
        global_blocks_raw=global_blocks,
        profile=profile,
        use_api=request.use_api,
        feeder_floor_id=request.floor_id,
    )
    yield sse_event(
        "progress",
        {
            "stage": "context_build",
            "status": "completed",
            "floors_discovered": floors_discovered,
            "api_success": api_success,
            "api_failed": api_failed,
        },
    )

    yield sse_event("progress", {"stage": "ttl_export", "status": "started"})
    graph, floor_count, global_block_count, _, _, _ = serialize_context_to_ttl(context)
    ttl = graph.serialize(format="turtle")
    if isinstance(ttl, bytes):
        ttl = ttl.decode("utf-8")
    yield sse_event(
        "progress",
        {"stage": "ttl_export", "status": "completed", "floors_exported": floor_count, "global_blocks": global_block_count},
    )

    yield sse_event(
        "complete",
        {
            "floor_id": request.floor_id,
            "profile_name": request.profile_name,
            "ttl": ttl,
        },
    )


def parse_payload_arg(payload_arg: str) -> dict[str, Any]:
    payload_path = Path(payload_arg)
    if payload_path.exists():
        loaded = load_json(str(payload_path))
        if isinstance(loaded, dict):
            return loaded
        raise ValueError("payload file must contain a JSON object")

    loaded = json.loads(payload_arg)
    if not isinstance(loaded, dict):
        raise ValueError("payload JSON must be an object")
    return loaded


def main() -> None:
    parser = argparse.ArgumentParser(
        description="One-call SSE-like flow: floor_id + profile_name + payload(hierarchy/global_blocks) -> Turtle."
    )
    parser.add_argument("--floor-id", required=True, help="Floor ID to call child-blocks API with.")
    parser.add_argument("--profile-name", required=True, help="Profile name key (resolved via Redis stub).")
    parser.add_argument(
        "--payload",
        required=True,
        help='JSON object string OR file path with {"hierarchy": {...}, "global_blocks": {...}}',
    )
    parser.add_argument("--no-api", action="store_true", help="Use stub child-block provider instead of API.")
    args = parser.parse_args()

    payload = parse_payload_arg(args.payload)
    req = ExportRequest(
        floor_id=args.floor_id,
        profile_name=args.profile_name,
        payload=payload,
        use_api=not args.no_api,
    )

    for event in stream_ttl_export(req):
        print(event, end="")


if __name__ == "__main__":
    main()
