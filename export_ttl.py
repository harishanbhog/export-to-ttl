#!/usr/bin/env python3
"""MVP exporter: xFloor federation JSON -> Turtle (.ttl)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from rdflib import Graph, Literal, Namespace, RDF, RDFS, OWL, XSD, URIRef

XF = Namespace("https://xfloor.ai/ontology#")
CAMPUS = Namespace("https://xfloor.ai/campus#")


def sanitize_fragment(value: str, fallback_prefix: str) -> str:
    """Create safe IRI fragment from runtime IDs/titles."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", (value or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or f"{fallback_prefix}_unknown"


def parse_flag_to_bool(value: Any) -> bool:
    """Normalize common runtime boolean formats ("1"/"0", true/false, yes/no)."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y"}


def looks_like_person_name(text: str) -> bool:
    """Very small heuristic for faculty-like leaf titles."""
    if not text:
        return False
    if text.startswith("Dr "):
        return True
    parts = [p for p in re.split(r"\s+", text) if p]
    if len(parts) < 2:
        return False
    alpha_parts = [p for p in parts if p.replace(".", "").isalpha()]
    return len(alpha_parts) >= 2 and all(p[0].isupper() for p in alpha_parts[:2])


def add_schema_declarations(graph: Graph) -> None:
    """Add minimal ontology + class/property declarations for readable TTL."""
    ontology = URIRef("https://xfloor.ai/ontology")
    graph.add((ontology, RDF.type, OWL.Ontology))
    graph.add((ontology, RDFS.label, Literal("xFloor MVP Ontology Export")))

    classes = [
        XF.Federation,
        XF.Floor,
        XF.HubFloor,
        XF.LeafFloor,
        XF.Block,
        XF.User,
        CAMPUS.InstitutionFloor,
        CAMPUS.DepartmentFloor,
        CAMPUS.FacultyFloor,
    ]
    for cls in classes:
        graph.add((cls, RDF.type, OWL.Class))

    object_props = [XF.hasChildFloor, XF.hasParentFloor, XF.hasBlock]
    for prop in object_props:
        graph.add((prop, RDF.type, OWL.ObjectProperty))

    data_props = [
        XF.floorId,
        XF.runtimeFloorId,
        XF.title,
        XF.description,
        XF.visibility,
        XF.isLeaf,
        XF.blockId,
        XF.blockTypeCode,
        XF.inheritsToChildFloors,
        XF.isDefaultBlock,
        XF.isLiveEnabled,
        XF.analyticsEnabled,
        XF.userAllowedToPost,
    ]
    for prop in data_props:
        graph.add((prop, RDF.type, OWL.DatatypeProperty))


def add_optional_literal(graph: Graph, subject: URIRef, predicate: URIRef, value: Any, datatype: URIRef | None = None) -> None:
    """Add literal only when value is present and non-empty."""
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    graph.add((subject, predicate, Literal(value, datatype=datatype)))


def export_graph(hierarchy: dict[str, Any], blocks_payload: dict[str, Any]) -> Graph:
    graph = Graph()
    graph.bind("xf", XF)
    graph.bind("campus", CAMPUS)
    graph.bind("rdf", RDF)
    graph.bind("rdfs", RDFS)
    graph.bind("owl", OWL)
    graph.bind("xsd", XSD)

    add_schema_declarations(graph)

    federation_nodes: list[URIRef] = []

    def walk_floor(node: dict[str, Any], parent_uri: URIRef | None = None, is_top_under_root: bool = False) -> URIRef | None:
        floor_id = node.get("id")
        if not floor_id:
            return None

        floor_uri = XF[sanitize_fragment(str(floor_id), "floor")]
        children = node.get("children") or []
        is_leaf = len(children) == 0

        graph.add((floor_uri, RDF.type, XF.Floor))
        graph.add((floor_uri, RDF.type, XF.LeafFloor if is_leaf else XF.HubFloor))
        graph.add((floor_uri, XF.floorId, Literal(str(floor_id))))
        graph.add((floor_uri, XF.isLeaf, Literal(is_leaf, datatype=XSD.boolean)))

        title = (node.get("title") or "").strip() or (node.get("name") or "")
        add_optional_literal(graph, floor_uri, XF.title, title)
        add_optional_literal(graph, floor_uri, XF.description, node.get("desc"))
        add_optional_literal(graph, floor_uri, XF.visibility, node.get("type"))
        add_optional_literal(graph, floor_uri, XF.runtimeFloorId, node.get("FID"))

        if "Department" in title:
            graph.add((floor_uri, RDF.type, CAMPUS.DepartmentFloor))
        if is_leaf and looks_like_person_name(title):
            graph.add((floor_uri, RDF.type, CAMPUS.FacultyFloor))

        if is_top_under_root:
            graph.add((floor_uri, RDF.type, XF.Federation))
            federation_nodes.append(floor_uri)

        if parent_uri is not None:
            graph.add((parent_uri, XF.hasChildFloor, floor_uri))
            graph.add((floor_uri, XF.hasParentFloor, parent_uri))

        for child in children:
            if isinstance(child, dict):
                walk_floor(child, parent_uri=floor_uri)

        return floor_uri

    root_children = hierarchy.get("children") or []
    for child in root_children:
        if isinstance(child, dict):
            walk_floor(child, is_top_under_root=True)

    top_federation = federation_nodes[0] if federation_nodes else None

    for block in blocks_payload.get("blocks", []):
        if not isinstance(block, dict):
            continue
        bid = block.get("BID")
        if not bid:
            continue

        block_uri = XF[f"block_{sanitize_fragment(str(bid), 'block')}"]
        graph.add((block_uri, RDF.type, XF.Block))
        graph.add((block_uri, XF.blockId, Literal(str(bid))))
        add_optional_literal(graph, block_uri, XF.title, block.get("title"))
        add_optional_literal(graph, block_uri, XF.blockTypeCode, block.get("type"))
        graph.add((block_uri, XF.inheritsToChildFloors, Literal(parse_flag_to_bool(block.get("display_child_floors")), datatype=XSD.boolean)))
        graph.add((block_uri, XF.isDefaultBlock, Literal(parse_flag_to_bool(block.get("default_block")), datatype=XSD.boolean)))
        graph.add((block_uri, XF.isLiveEnabled, Literal(parse_flag_to_bool(block.get("is_live_enabled")), datatype=XSD.boolean)))
        graph.add((block_uri, XF.analyticsEnabled, Literal(parse_flag_to_bool(block.get("analytics_enabled")), datatype=XSD.boolean)))
        graph.add((block_uri, XF.userAllowedToPost, Literal(parse_flag_to_bool(block.get("user_allowed_to_post")), datatype=XSD.boolean)))

        if top_federation is not None:
            graph.add((top_federation, XF.hasBlock, block_uri))

    return graph


def main() -> None:
    parser = argparse.ArgumentParser(description="Export xFloor hierarchy and blocks JSON into Turtle ontology.")
    parser.add_argument("--hierarchy", required=True, help="Path to hierarchy JSON file.")
    parser.add_argument("--blocks", required=True, help="Path to blocks JSON file.")
    parser.add_argument("--out", required=True, help="Path to output .ttl file.")
    args = parser.parse_args()

    hierarchy = json.loads(Path(args.hierarchy).read_text(encoding="utf-8"))
    blocks_payload = json.loads(Path(args.blocks).read_text(encoding="utf-8"))

    graph = export_graph(hierarchy, blocks_payload)
    graph.serialize(destination=args.out, format="turtle")

    print(f"Exported Turtle: {args.out}")
    print("\nExample snippet (one floor + one block):")
    print("""@prefix xf: <https://xfloor.ai/ontology#> .

xf:setspr a xf:Floor, xf:HubFloor, xf:Federation ;
    xf:floorId \"setspr\" ;
    xf:title \"setspr\" .

xf:block_1776142091308 a xf:Block ;
    xf:blockId \"1776142091308\" ;
    xf:title \"Feeds\" .""")


if __name__ == "__main__":
    main()
