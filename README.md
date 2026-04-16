# xFloor Ontology Export MVP (Context-First Architecture + SSE-style one-call flow)

This MVP uses a **two-step flow**:
1. Build composed export context JSON.
2. Export Turtle from that context.

It also now includes a **single-call orchestration flow** (CLI simulation of a FastAPI + SSE endpoint), where one request carries:
- `floor_id`
- `profile_name`
- one payload JSON object containing both:
  - `hierarchy`
  - `global_blocks`

## Requirements
- Python 3.11+
- `rdflib`
- `requests` (needed only for `--use-api` mode)

## Step 1: Build export context

```bash
python build_export_context.py \
  --hierarchy sample_hierarchy.json \
  --global-blocks sample_global_blocks.json \
  --profile sample_profile.json \
  --out sample_export_context.json
```

Optional real API mode:
```bash
python build_export_context.py \
  --hierarchy sample_hierarchy.json \
  --global-blocks sample_global_blocks.json \
  --profile sample_profile.json \
  --out sample_export_context.json \
  --use-api
```

### Child blocks API handler

When `--use-api` is enabled, builder calls:

`https://floortv.in/api/memory/floor/child/blocks/{floor_id}?user_id=<USER_ID>&app_id=<APP_ID>`

- `floor_id` comes from hierarchy federation/root node.
- `user_id` and `app_id` are loaded from `.env` / environment.
- if API fails, builder falls back to local stub and logs an error entry.

Supported API response format includes:
- `{ "list": [{"fed_path": "...", "blocks": [...]}, ...] }`

All block properties from API are retained in context `floor_blocks`.

### Environment /.env values

Required for `--use-api`:
- `USER_ID` (or `XFLOOR_USER_ID`)
- `APP_ID` (or `XFLOOR_APP_ID`)

Optional:
- `XFLOOR_TOKEN` (or `TOKEN` / `BEARER_TOKEN`)
- `BASE_URL` (defaults to `https://floortv.in/api/memory/`)

Example `.env`:
```env
USER_ID=1754011711033
APP_ID=1754011711033
XFLOOR_TOKEN=YOUR_TOKEN
```

## Step 2: Export Turtle

```bash
python export_ttl.py --context sample_export_context.json --out sample_output.ttl
```

---

## Single-call SSE-style flow (for FastAPI integration target)

This flow is implemented in `sse_export_service.py` and is designed to match how you'd wire a FastAPI endpoint with SSE updates:

### Request contract

Inputs:
1. `floor_id` (used to call child-blocks API)
2. `profile_name` (profile resolved from Redis; stubbed currently)
3. `payload` (JSON object with both hierarchy + global blocks):

```json
{
  "hierarchy": { "...": "..." },
  "global_blocks": {
    "blocks": [ ... ]
  }
}
```

### What happens inside

1. Emits SSE progress: `profile_lookup started`
2. Fetches profile by `profile_name` via Redis stub (`fetch_profile_from_redis_stub`)
3. Emits SSE progress: `context_build started`
4. Calls the existing context builder with provided `floor_id` (API/stub behavior unchanged)
5. Emits SSE progress: `context_build completed`
6. Emits SSE progress: `ttl_export started`
7. Calls existing TTL serializer (business logic unchanged)
8. Emits SSE `complete` event containing generated TTL

### Run locally

#### Option A: payload from file

Create a combined payload file:

```json
{
  "hierarchy": { /* copy from sample_hierarchy.json */ },
  "global_blocks": { /* copy from sample_global_blocks.json */ }
}
```

Then run:

```bash
python sse_export_service.py \
  --floor-id setspr_sdc_kan \
  --profile-name campus \
  --payload sample_combined_payload.json \
  --no-api
```

This prints SSE-formatted output to stdout:

```text
event: progress
data: {"stage":"profile_lookup","status":"started"}

event: progress
data: {"stage":"profile_lookup","status":"completed"}

...

event: complete
data: {"floor_id":"...","profile_name":"...","ttl":"@prefix ..."}
```

#### Option B: payload as inline JSON

```bash
python sse_export_service.py \
  --floor-id setspr_sdc_kan \
  --profile-name campus \
  --payload '{"hierarchy": {...}, "global_blocks": {"blocks": [...]}}' \
  --no-api
```

### API mode notes

To run with live API (omit `--no-api`), ensure `.env` / environment has:
- `USER_ID` (or `XFLOOR_USER_ID`)
- `APP_ID` (or `XFLOOR_APP_ID`)

Optional:
- `XFLOOR_TOKEN` (or `TOKEN` / `BEARER_TOKEN`)
- `BASE_URL` (defaults to `https://floortv.in/api/memory/`)

### FastAPI integration sketch

In your FastAPI server, map your endpoint to call `stream_ttl_export(...)` and return it through `StreamingResponse` with media type `text/event-stream`.

## Notes
- Stub mode remains default for offline runs.
- This is MVP behavior; inheritance/local semantics are still approximated.


Context `floors` section now contains only floors returned by child-blocks provider (non-empty block lists), not all hierarchy floors.
