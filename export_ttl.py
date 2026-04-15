#!/usr/bin/env python3
"""xFloor JSON -> Turtle exporter (MVP, domain-agnostic + profile-driven)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from rdflib import Graph, Literal, Namespace, OWL, RDF, RDFS, URIRef, XSD

XF = Namespace("https://xfloor.ai/ontology#")

BASE_CLASSES = [
    XF.Federation,
    XF.Floor,
    XF.HubFloor,
    XF.LeafFloor,
    XF.ChildFloor,
    XF.NodeFloor,
    XF.Block,
    XF.User,
]

BASE_OBJECT_PROPERTIES = [
    XF.hasRootHub,
    XF.hasChildFloor,
    XF.hasParentFloor,
    XF.hasBlock,
    XF.hasGlobalBlock,
    XF.hasLocalBlock,
    XF.originFloor,
    XF.managedBy,
    XF.hasCoOwner,
]

BASE_DATA_PROPERTIES = [
    XF.floorId,
    XF.runtimeFloorId,
    XF.blockId,
    XF.title,
    XF.description,
    XF.visibility,
    XF.isLeaf,
    XF.floorCategory,
    XF.phoneNumber,
    XF.emailId,
    XF.blockTypeCode,
    XF.inheritsToChildFloors,
    XF.isDefaultBlock,
    XF.isLiveEnabled,
    XF.analyticsEnabled,
    XF.userAllowedToPost,
    XF.isDerivedBlock,
    XF.isEditableByLocalOwner,
]


def sanitize_fragment(value: str, fallback_prefix: str) -> str:
    """Create safe IRI fragment from runtime IDs."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", (value or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or f"{fallback_prefix}_unknown"


def parse_flag_to_bool(value: Any) -> bool:
    """Normalize common runtime booleans such as 1/0, true/false."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def add_optional_literal(
    graph: Graph,
    subject: URIRef,
    predicate: URIRef,
    value: Any,
    datatype: URIRef | None = None,
) -> None:
    """Add a literal triple only if the value is present and non-empty."""
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    graph.add((subject, predicate, Literal(value, datatype=datatype)))


def resolve_curie(curie: str, prefix_map: dict[str, Namespace]) -> URIRef | None:
    """Resolve CURIE like 'campus:DepartmentFloor' to a URIRef."""
    if not curie or ":" not in curie:
        return None
    prefix, local_name = curie.split(":", 1)
    namespace = prefix_map.get(prefix)
    if namespace is None or not local_name:
        return None
    return namespace[local_name]


def add_base_schema_declarations(graph: Graph) -> None:
    """Declare ontology header and base xFloor classes/properties."""
    ontology = URIRef("https://xfloor.ai/ontology")
    graph.add((ontology, RDF.type, OWL.Ontology))
    graph.add((ontology, RDFS.label, Literal("xFloor MVP Ontology Export")))

    for cls in BASE_CLASSES:
        graph.add((cls, RDF.type, OWL.Class))

    for prop in BASE_OBJECT_PROPERTIES:
        graph.add((prop, RDF.type, OWL.ObjectProperty))

    for prop in BASE_DATA_PROPERTIES:
        graph.add((prop, RDF.type, OWL.DatatypeProperty))


def load_profile(profile_path: str | None) -> dict[str, Any] | None:
    """Load optional domain profile JSON."""
    if not profile_path:
        return None
    raw = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Profile JSON must be an object")
    return raw


def export_graph(
    hierarchy: dict[str, Any],
    blocks_payload: dict[str, Any],
    profile: dict[str, Any] | None = None,
) -> tuple[Graph, int, int, URIRef | None]:
    """Export hierarchy + blocks into an RDF graph."""
    graph = Graph()
    graph.bind("xf", XF)
    graph.bind("rdf", RDF)
    graph.bind("rdfs", RDFS)
    graph.bind("owl", OWL)
    graph.bind("xsd", XSD)

    prefix_map: dict[str, Namespace] = {"xf": XF}

    if profile:
        profile_prefix = str(profile.get("namespace_prefix") or "").strip()
        profile_uri = str(profile.get("namespace_uri") or "").strip()
        if profile_prefix and profile_uri:
            profile_ns = Namespace(profile_uri)
            graph.bind(profile_prefix, profile_ns)
            prefix_map[profile_prefix] = profile_ns

    add_base_schema_declarations(graph)

    if profile:
        for class_curie in profile.get("declare_classes", []):
            if not isinstance(class_curie, str):
                continue
            class_uri = resolve_curie(class_curie, prefix_map)
            if class_uri is not None:
                graph.add((class_uri, RDF.type, OWL.Class))

    floor_category_map: dict[str, str] = profile.get("floor_category_map", {}) if profile else {}
    block_title_map: dict[str, str] = profile.get("block_title_map", {}) if profile else {}

    floor_count = 0
    block_count = 0
    root_hub_uri: URIRef | None = None

    def walk_floor(node: dict[str, Any], parent_uri: URIRef | None = None, top_under_root: bool = False) -> URIRef | None:
        nonlocal floor_count, root_hub_uri

        floor_id = node.get("id")
        if not floor_id:
            return None

        floor_uri = XF[sanitize_fragment(str(floor_id), "floor")]
        children = node.get("children") or []
        is_leaf = len(children) == 0

        graph.add((floor_uri, RDF.type, XF.Floor))
        if top_under_root:
            graph.add((floor_uri, RDF.type, XF.HubFloor))
            graph.add((floor_uri, RDF.type, XF.Federation))
            root_hub_uri = floor_uri
        else:
            graph.add((floor_uri, RDF.type, XF.NodeFloor if is_leaf else XF.ChildFloor))

        graph.add((floor_uri, XF.floorId, Literal(str(floor_id))))
        graph.add((floor_uri, XF.isLeaf, Literal(is_leaf, datatype=XSD.boolean)))

        title = (node.get("title") or "").strip() or (node.get("name") or "")
        add_optional_literal(graph, floor_uri, XF.title, title)
        add_optional_literal(graph, floor_uri, XF.description, node.get("desc"))
        add_optional_literal(graph, floor_uri, XF.visibility, node.get("type"))
        add_optional_literal(graph, floor_uri, XF.runtimeFloorId, node.get("FID"))
        add_optional_literal(graph, floor_uri, XF.floorCategory, node.get("floor_cat"))
        add_optional_literal(graph, floor_uri, XF.phoneNumber, node.get("phone"))
        add_optional_literal(graph, floor_uri, XF.emailId, node.get("email"))

        floor_cat = node.get("floor_cat")
        if isinstance(floor_cat, str):
            mapped_curie = floor_category_map.get(floor_cat)
            mapped_uri = resolve_curie(mapped_curie, prefix_map) if isinstance(mapped_curie, str) else None
            if mapped_uri is not None:
                graph.add((floor_uri, RDF.type, mapped_uri))

        if parent_uri is not None:
            graph.add((parent_uri, XF.hasChildFloor, floor_uri))
            graph.add((floor_uri, XF.hasParentFloor, parent_uri))

        floor_count += 1

        for child in children:
            if isinstance(child, dict):
                walk_floor(child, parent_uri=floor_uri)

        return floor_uri

    for child in hierarchy.get("children", []):
        if isinstance(child, dict):
            walk_floor(child, top_under_root=True)

    seen_block_ids: set[str] = set()

    for block in blocks_payload.get("blocks", []):
        if not isinstance(block, dict):
            continue

        bid = block.get("BID")
        if not bid:
            continue

        bid_text = str(bid)
        if bid_text in seen_block_ids:
            continue
        seen_block_ids.add(bid_text)

        block_uri = XF[f"block_{sanitize_fragment(bid_text, 'block')}"]
        graph.add((block_uri, RDF.type, XF.Block))
        graph.add((block_uri, XF.blockId, Literal(bid_text)))
        add_optional_literal(graph, block_uri, XF.title, block.get("title"))
        add_optional_literal(graph, block_uri, XF.blockTypeCode, block.get("type"))

        inherits = parse_flag_to_bool(block.get("display_child_floors"))
        graph.add((block_uri, XF.inheritsToChildFloors, Literal(inherits, datatype=XSD.boolean)))
        graph.add((block_uri, XF.isDerivedBlock, Literal(inherits, datatype=XSD.boolean)))
        graph.add((block_uri, XF.isEditableByLocalOwner, Literal(False if inherits else True, datatype=XSD.boolean)))

        graph.add((block_uri, XF.isDefaultBlock, Literal(parse_flag_to_bool(block.get("default_block")), datatype=XSD.boolean)))
        graph.add((block_uri, XF.isLiveEnabled, Literal(parse_flag_to_bool(block.get("is_live_enabled")), datatype=XSD.boolean)))
        graph.add((block_uri, XF.analyticsEnabled, Literal(parse_flag_to_bool(block.get("analytics_enabled")), datatype=XSD.boolean)))
        graph.add((block_uri, XF.userAllowedToPost, Literal(parse_flag_to_bool(block.get("user_allowed_to_post")), datatype=XSD.boolean)))

        block_title = block.get("title")
        if isinstance(block_title, str):
            mapped_curie = block_title_map.get(block_title)
            mapped_uri = resolve_curie(mapped_curie, prefix_map) if isinstance(mapped_curie, str) else None
            if mapped_uri is not None:
                graph.add((block_uri, RDF.type, mapped_uri))

        if root_hub_uri is not None:
            graph.add((root_hub_uri, XF.hasGlobalBlock, block_uri))
            if inherits:
                graph.add((block_uri, XF.originFloor, root_hub_uri))

        block_count += 1

    return graph, floor_count, block_count, root_hub_uri


def main() -> None:
    parser = argparse.ArgumentParser(description="Export xFloor hierarchy + blocks JSON into Turtle ontology.")
    parser.add_argument("--hierarchy", required=True, help="Path to hierarchy JSON file.")
    parser.add_argument("--blocks", required=True, help="Path to blocks JSON file.")
    parser.add_argument("--out", required=True, help="Path to output .ttl file.")
    parser.add_argument("--profile", required=False, help="Optional path to domain profile JSON.")
    args = parser.parse_args()

    hierarchy = json.loads(Path(args.hierarchy).read_text(encoding="utf-8"))
    blocks_payload = json.loads(Path(args.blocks).read_text(encoding="utf-8"))
    profile = load_profile(args.profile)

    graph, floor_count, block_count, _ = export_graph(hierarchy, blocks_payload, profile=profile)
    graph.serialize(destination=args.out, format="turtle")

    print(f"Exported Turtle: {args.out}")
    print(
        "Summary: "
        f"floors_exported={floor_count}, "
        f"blocks_exported={block_count}, "
        f"profile_used={'yes' if profile else 'no'}"
    )
    print("\nExample snippet (one floor + one block):")
    print("""@prefix xf: <https://xfloor.ai/ontology#> .

xf:setspr a xf:Floor, xf:HubFloor, xf:Federation ;
    xf:floorId \"setspr\" ;
    xf:floorCategory \"Institution Floor\" ;
    xf:title \"SETSPR\" .

xf:block_1776142091308 a xf:Block ;
    xf:blockId \"1776142091308\" ;
    xf:inheritsToChildFloors true ;
    xf:title \"Feeds\" .""")


if __name__ == "__main__":
    main()
