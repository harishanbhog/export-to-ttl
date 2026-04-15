# xFloor Ontology Export MVP (Context-First Architecture)

This MVP uses a **two-step flow**:

1. Build a composed export context JSON (`ontology_export_context.json` style).
2. Export Turtle (`.ttl`) from that composed context.

This keeps the exporter simple and closer to xFloor runtime reality.

## Why `ontology_export_context.json` exists

The context file merges all runtime sources into one export-ready object:
- hierarchy (`hierarchy.json`)
- global hub blocks (`global_blocks.json`)
- per-floor effective blocks + metadata (from floor info API)
- optional profile mapping (domain typing)
- fetch errors (without aborting the whole run)

Once this context exists, the Turtle exporter reads only that file.

## Files

- `build_export_context.py` – preprocessing/composition step
- `export_ttl.py` – Turtle exporter from composed context
- `requirements.txt`
- `sample_hierarchy.json`
- `sample_global_blocks.json`
- `sample_profile.json`
- `sample_export_context.json`
- `sample_output.ttl`

## Requirements

- Python 3.11+
- `requests`
- `rdflib`

## Step 1: Build export context

```bash
python build_export_context.py \
  --hierarchy sample_hierarchy.json \
  --global-blocks sample_global_blocks.json \
  --profile sample_profile.json \
  --base-url https://appfloor.in \
  --token YOUR_TOKEN \
  --out sample_export_context.json
```

What it does:
- traverses hierarchy and collects all `floor_id`s
- calls `GET /api/memory/floor/info/{floor_id}` with Bearer token
- collects floor metadata + `floor_blocks` (effective blocks in V1)
- normalizes global blocks
- writes one composed JSON context
- logs success/failure counts and stores failures under `errors[]`

## Step 2: Export Turtle

```bash
python export_ttl.py --context sample_export_context.json --out sample_output.ttl
```

What it does:
- loads only composed context JSON
- emits base xFloor ontology vocabulary (classes/properties)
- uses hierarchy for floor structure and parent-child relations
- uses floor map for API-preferred metadata (with safe fallback to hierarchy)
- exports global blocks on root hub (`hasBlock`, `hasGlobalBlock`)
- exports per-floor visible blocks (`hasBlock`) and approximates local blocks (`hasLocalBlock` if block not in global set)
- applies optional profile-based floor and block typing via mappings

## V1 scope / non-goals

- no import-back functionality
- no full ACL ontology
- no full validation ontology
- no perfect inheritance reconstruction
- local-vs-inherited is an approximation based on global block ID membership

## Floor info API used

`GET /api/memory/floor/info/{floor_id}`

Auth:
- `Authorization: Bearer <token>`

The builder tolerates failures per floor and continues, recording issues in `errors`.
