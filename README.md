# xFloor Ontology Export MVP (Context-First Architecture)

This MVP uses a **two-step flow**:
1. Build composed export context JSON.
2. Export Turtle from that context.

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
- `{ "list": [{"floor_id": "...", "blocks": [...]}, ...] }`

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

## Notes
- Stub mode remains default for offline runs.
- This is MVP behavior; inheritance/local semantics are still approximated.
