# xFloor JSON → Turtle Exporter (MVP, Domain-Agnostic + Profile-Driven)

This project exports xFloor runtime JSON into a Protégé/WebProtégé-compatible Turtle (`.ttl`) file.

## What this exporter does

This V1 exporter reads:
- `hierarchy.json` (floor hierarchy)
- `blocks.json` (runtime block definitions)
- optional `profile.json` (domain typing rules)

and writes:
- `xfloor_export.ttl` (or any file path passed via `--out`)

## Base xFloor ontology vocabulary (always exported)

The exporter always declares and uses the base xFloor ontology namespace:
- `xf: https://xfloor.ai/ontology#`

It also always binds:
- `rdf:`
- `rdfs:`
- `owl:`
- `xsd:`

It always declares base classes/properties (e.g. `xf:Floor`, `xf:Block`, `xf:hasChildFloor`, `xf:hasGlobalBlock`, `xf:floorCategory`, etc.), even when no domain profile is provided.

## Base ontology vs profile ontology

- **Base xFloor ontology**: generic graph structure and metadata used for all exports.
- **Optional domain profile**: domain-specific class typing rules loaded from JSON at runtime.

The exporter core is domain-agnostic. It does **not** hardcode campus-specific semantics.

## `floor_cat` behavior

`floor_cat` is treated as a runtime semantic hint:
- always exported as a literal (`xf:floorCategory`) when present
- optionally mapped to a domain class using `profile.floor_category_map`

If no mapping is found, export still succeeds with generic xFloor typing (`xf:HubFloor` / `xf:ChildFloor` / `xf:NodeFloor`).

## Federation/hub behavior in V1

In this MVP, the top meaningful node under `root` **doubles as the federation root hub**.
It is typed as:
- `xf:HubFloor`

All non-root floors are typed as:
- `xf:ChildFloor` (if they have children)
- `xf:NodeFloor` (if they are leaves)

No separate federation wrapper individual is created in V1.

## Global block behavior in V1

All blocks from `blocks.json` are treated as global blocks attached to the federation root hub using:
- `xf:hasGlobalBlock`

(Using only one root-hub block relationship avoids duplicate block listings in V1 exports.)

If `display_child_floors == "1"`, exporter sets:
- `xf:inheritsToChildFloors true`
- `xf:isDerivedBlock true`
- `xf:isEditableByLocalOwner false`
- `xf:originFloor <root_hub>`

If `display_child_floors == "0"`, exporter sets:
- `xf:inheritsToChildFloors false`
- `xf:isDerivedBlock false`
- `xf:isEditableByLocalOwner true`

`xf:hasLocalBlock` is declared in vocabulary, but local child block export is not implemented in V1.

## Files

- `export_ttl.py`
- `requirements.txt`
- `sample_hierarchy.json`
- `sample_blocks.json`
- `sample_profile.json`
- `sample_output.ttl`

## Requirements

- Python 3.11+
- `rdflib`

## Setup

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Run (with profile)

```bash
python export_ttl.py --hierarchy sample_hierarchy.json --blocks sample_blocks.json --profile sample_profile.json --out sample_output.ttl
```

## Run (without profile)

```bash
python export_ttl.py --hierarchy sample_hierarchy.json --blocks sample_blocks.json --out sample_output.ttl
```

## What V1 exports

- floor/block individuals
- hierarchy links (`xf:hasChildFloor`, `xf:hasParentFloor`)
- federation root hub + global blocks
- base metadata (`title`, `description`, `visibility`, `FID`, `floor_cat`, `phone`, `email`, block flags)
- optional domain class typing from profile mappings

## Non-goals (V1)

- no import-back functionality
- no full ACL ontology modeling
- no full validation ontology
- no local child block export
- no advanced OWL reasoning
