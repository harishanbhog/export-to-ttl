# xFloor JSON → Turtle MVP Exporter

This repository contains a **simple MVP prototype** that converts xFloor runtime federation JSON into a Protégé/WebProtégé-friendly Turtle (`.ttl`) export.

It intentionally keeps the model small and readable:
- exports floor hierarchy and blocks
- emits RDF/OWL style class/property declarations
- creates floor/block individuals with basic mappings
- includes optional campus typing heuristics

## Files

- `export_ttl.py` – exporter script
- `requirements.txt` – Python dependency list
- `sample_hierarchy.json` – sample hierarchy input
- `sample_blocks.json` – sample blocks input
- `sample_output.ttl` – example generated Turtle output

## Requirements

- Python 3.11+
- `rdflib`

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python export_ttl.py --hierarchy sample_hierarchy.json --blocks sample_blocks.json --out sample_output.ttl
```

## Mapping summary (MVP)

- Floor node with `id` => RDF individual (`xf:Floor`)
- Children present => `xf:HubFloor`; no children => `xf:LeafFloor`
- Top meaningful children under `root` => also typed `xf:Federation`
- Parent/child links: `xf:hasChildFloor` and `xf:hasParentFloor`
- Blocks => `xf:Block`, attached to top federation via `xf:hasBlock`
- Runtime flags (`"1"`/`"0"`) converted to RDF booleans

### Optional campus typing heuristic

- title contains `Department` => `campus:DepartmentFloor`
- leaf title starts with `Dr ` or appears person-like => `campus:FacultyFloor`

## Notes

- This is an MVP exporter from xFloor runtime JSON to Protégé-compatible Turtle.
- Import-back, ACL modeling, and full validation ontology are intentionally out of scope for V1.
