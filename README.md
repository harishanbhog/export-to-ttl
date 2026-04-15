# xFloor Ontology Export MVP (Context-First Architecture)

This MVP uses a **two-step flow**:

1. Build a composed export context JSON (`ontology_export_context.json` style).
2. Export Turtle (`.ttl`) from that composed context.

## Why `ontology_export_context.json` exists

The context file merges runtime sources into one export-ready object:
- hierarchy (`hierarchy.json`)
- global hub blocks (`global_blocks.json`)
- per-floor visible blocks from child-blocks API
- optional profile mapping (domain typing)
- API/fetch errors (without aborting the run)

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
  --out sample_export_context.json
  # add --use-api to call real API handler
```

What it does:
- traverses hierarchy and collects all `floor_id`s
- uses a local stub by default for child blocks
- optional real API handler: `GET <baseURL>/floor/child/blocks/{feeder_id}` via `--use-api`
- maps stubbed child floor IDs to each floor's `floor_blocks`
- normalizes global blocks
- writes one composed JSON context
- logs success/failure and stores issues in `errors[]`

> Default implementation is **stub mode**.
> Stubbed child floors with dummy blocks: `setspr_sdc_kan`, `setspr_sdc_kan_venkaborao`.

Real API mode (with fallback to stub on failure):
```bash
python build_export_context.py --hierarchy sample_hierarchy.json --global-blocks sample_global_blocks.json --profile sample_profile.json --base-url https://appfloor.in --out sample_export_context.json --use-api
```

Token loading order for `build_export_context.py`:
1. `--token` CLI argument (optional override)
2. environment variables: `XFLOOR_TOKEN`, `TOKEN`, `BEARER_TOKEN`
3. `.env` file keys: `XFLOOR_TOKEN`, `TOKEN`, `BEARER_TOKEN`

Example `.env`:
```
XFLOOR_TOKEN=YOUR_TOKEN
```

## Step 2: Export Turtle

```bash
python export_ttl.py --context sample_export_context.json --out sample_output.ttl
```

What it does:
- loads only composed context JSON
- emits base xFloor ontology vocabulary (classes/properties)
- uses hierarchy for floor structure and parent-child relations
- uses context floor map for floor-level metadata and floor-visible blocks
- exports global blocks on root hub (`hasBlock`, `hasGlobalBlock`)
- exports per-floor visible blocks (`hasBlock`) and approximates local blocks (`hasLocalBlock` if block ID not in global set)
- applies optional profile-based floor and block typing via mappings


Campus profile typing rule in exporter (level-based):
- level 0 -> `campus:UniversityFloor`
- level 1 -> `campus:InstitutionFloor`
- level 2 -> `campus:DepartmentFloor`
- level 3+ -> `campus:FacultyFloor`

Also, xFloor structural typing is:
- federation/root floor -> `xf:HubFloor`
- non-root with children -> `xf:ChildFloor`
- non-root leaf -> `xf:NodeFloor`


Mandatory floor metadata in exporter:
- `xf:phoneNumber`
- `xf:emailId`
- `xf:location`

If missing in context/hierarchy, exporter writes `"unknown"` as fallback.

## V1 scope / non-goals

- no import-back functionality
- no full ACL ontology
- no full validation ontology
- no perfect inheritance reconstruction
- local-vs-inherited is an approximation based on global block ID membership
