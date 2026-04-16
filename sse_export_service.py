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
    ttl_out: str = "generated_output.ttl"


def sse_event(event: str, data: dict[str, Any]) -> str:
    """Format one SSE event frame.

    Example return:
    event: progress
    data: {"stage":"context_build","status":"started"}

    """
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def fetch_profile_from_redis_stub(profile_name: str) -> dict[str, Any]:
    """Stub for profile lookup from Redis.

    Replace with real Redis lookup in integration layer.

    Workflow note:
    - For local development, this attempts to load `sample_profile.json`.
    - If sample isn't present, returns a minimal profile envelope.

    Example integration replacement:
    - GET redis key `profile:{profile_name}`
    - JSON-decode into same shape returned here.
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
    """Orchestrate one-call export and stream SSE progress updates.

    End-to-end workflow:
    1) Validate payload shape (`hierarchy`, `global_blocks`).
    2) Fetch profile by name (stubbed Redis call).
    3) Build export context using caller `floor_id` (API only).
    4) Serialize context to TTL (existing business logic).
    5) Write TTL to output file and log file path.
    6) Yield `complete` event with TTL payload.

    This generator is intentionally FastAPI-friendly:
    it can be returned via `StreamingResponse(..., media_type="text/event-stream")`.

    Example:
    >>> req = ExportRequest("setspr_sdc_kan", "campus", payload, use_api=False)
    >>> for ev in stream_ttl_export(req):
    ...     print(ev, end="")
    """
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

    out_path = Path(request.ttl_out)
    out_path.write_text(ttl, encoding="utf-8")
    print(f"[sse-export] wrote ttl file: {out_path}")

    yield sse_event(
        "progress",
        {
            "stage": "ttl_export",
            "status": "completed",
            "floors_exported": floor_count,
            "global_blocks": global_block_count,
            "ttl_out": str(out_path),
        },
    )

    yield sse_event(
        "complete",
        {
            "floor_id": request.floor_id,
            "profile_name": request.profile_name,
            "ttl_out": str(out_path),
            "ttl": ttl,
        },
    )


def parse_payload_arg(payload_arg: str) -> dict[str, Any]:
    """Parse payload CLI arg as file-path or inline JSON object.

    Example file mode:
    --payload sample_combined_payload.json

    Example inline mode:
    --payload '{"hierarchy": {...}, "global_blocks": {...}}'
    """
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
    """CLI entrypoint for local simulation of endpoint + SSE stream.

    This command is for developer testing before FastAPI integration.
    """
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
    parser.add_argument("--ttl-out", default="generated_output.ttl", help="Path to write generated Turtle output.")
    args = parser.parse_args()

    payload = parse_payload_arg(args.payload)
    req = ExportRequest(
        floor_id=args.floor_id,
        profile_name=args.profile_name,
        payload=payload,
        use_api=True,
        ttl_out=args.ttl_out,
    )

    for event in stream_ttl_export(req):
        print(event, end="")


if __name__ == "__main__":
    main()
