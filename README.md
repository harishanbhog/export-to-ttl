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
# Linux/macOS
source .venv/bin/activate
# Windows (PowerShell)
# .venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt
```

## If `pip install -r requirements.txt` fails with `No matching distribution found`

If you also see connection errors such as `getaddrinfo failed`, that usually means **network/DNS/proxy access to PyPI is blocked**, not that `rdflib` is unavailable.

Try the following in order:

1. Verify Python version:
   ```bash
   python --version
   ```
   Must be 3.11+ for this MVP.

2. Test DNS/network to PyPI:
   ```bash
   nslookup pypi.org
   ```

3. If your environment uses a corporate proxy, configure pip:
   ```bash
   pip install --proxy http://USERNAME:PASSWORD@PROXY_HOST:PORT -r requirements.txt
   ```

4. Use an internal mirror (if your org provides one):
   ```bash
   pip install --index-url https://<your-mirror>/simple -r requirements.txt
   ```

5. Offline install using wheel file:
   - On a machine with internet:
     ```bash
     pip download rdflib -d wheels
     ```
   - Copy `wheels/` to your target machine, then:
     ```bash
     pip install --no-index --find-links wheels rdflib
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
