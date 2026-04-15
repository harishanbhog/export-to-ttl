#!/usr/bin/env python3
"""Export xFloor ontology Turtle from composed ontology_export_context.json (MVP)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from rdflib import Graph, Literal, Namespace, OWL, RDF, RDFS, URIRef, XSD

XF = Namespace("https://xfloor.ai/ontology#")

BASE_CLASSES = [XF.Federation, XF.Floor, XF.HubFloor, XF.LeafFloor, XF.Block, XF.User]
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
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", (value or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or f"{fallback_prefix}_unknown"


def parse_flag_to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def add_optional_literal(graph: Graph, s: URIRef, p: URIRef, value: Any, datatype: URIRef | None = None) -> None:
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    graph.add((s, p, Literal(value, datatype=datatype)))


def resolve_curie(curie: str | None, prefix_map: dict[str, Namespace]) -> URIRef | None:
    if not curie or ":" not in curie:
        return None
    prefix, local = curie.split(":", 1)
    ns = prefix_map.get(prefix)
    if ns is None or not local:
        return None
    return ns[local]


def add_base_schema_declarations(graph: Graph) -> None:
    ontology = URIRef("https://xfloor.ai/ontology")
    graph.add((ontology, RDF.type, OWL.Ontology))
    graph.add((ontology, RDFS.label, Literal("xFloor MVP Ontology Export")))

    for cls in BASE_CLASSES:
        graph.add((cls, RDF.type, OWL.Class))
    for prop in BASE_OBJECT_PROPERTIES:
        graph.add((prop, RDF.type, OWL.ObjectProperty))
    for prop in BASE_DATA_PROPERTIES:
        graph.add((prop, RDF.type, OWL.DatatypeProperty))


def serialize_context_to_ttl(context: dict[str, Any]) -> tuple[Graph, int, int, URIRef | None, URIRef | None]:
    hierarchy = context.get("hierarchy", {}) if isinstance(context.get("hierarchy"), dict) else {}
    floor_map = context.get("floors", {}) if isinstance(context.get("floors"), dict) else {}
    global_blocks = context.get("global_blocks", []) if isinstance(context.get("global_blocks"), list) else []
    profile = context.get("profile", {}) if isinstance(context.get("profile"), dict) else {}

    graph = Graph()
    graph.bind("xf", XF)
    graph.bind("rdf", RDF)
    graph.bind("rdfs", RDFS)
    graph.bind("owl", OWL)
    graph.bind("xsd", XSD)

    prefix_map: dict[str, Namespace] = {"xf": XF}
    profile_prefix = str(profile.get("namespace_prefix") or "").strip()
    profile_uri = str(profile.get("namespace_uri") or "").strip()
    if profile_prefix and profile_uri:
        pns = Namespace(profile_uri)
        graph.bind(profile_prefix, pns)
        prefix_map[profile_prefix] = pns

    add_base_schema_declarations(graph)

    for curie in profile.get("declare_classes", []) or []:
        uri = resolve_curie(curie, prefix_map)
        if uri is not None:
            graph.add((uri, RDF.type, OWL.Class))

    floor_category_map = profile.get("floor_category_map", {}) if isinstance(profile.get("floor_category_map"), dict) else {}
    block_title_map = profile.get("block_title_map", {}) if isinstance(profile.get("block_title_map"), dict) else {}

    floor_count = 0
    block_count = 0
    root_hub_uri: URIRef | None = None
    one_local_block_uri: URIRef | None = None

    # first pass floors + hierarchy
    def walk(node: dict[str, Any], parent_uri: URIRef | None = None, top_under_root: bool = False) -> None:
        nonlocal floor_count, root_hub_uri

        floor_id = node.get("id")
        if not floor_id:
            return

        floor_id_text = str(floor_id)
        floor_uri = XF[sanitize_fragment(floor_id_text, "floor")]
        children = node.get("children") or []
        is_leaf = len(children) == 0
        floor_api = floor_map.get(floor_id_text, {}) if isinstance(floor_map.get(floor_id_text), dict) else {}

        graph.add((floor_uri, RDF.type, XF.Floor))
        graph.add((floor_uri, RDF.type, XF.LeafFloor if is_leaf else XF.HubFloor))
        if top_under_root:
            graph.add((floor_uri, RDF.type, XF.Federation))
            root_hub_uri = floor_uri

        graph.add((floor_uri, XF.floorId, Literal(floor_id_text)))
        graph.add((floor_uri, XF.isLeaf, Literal(is_leaf, datatype=XSD.boolean)))

        title = floor_api.get("title") or node.get("title") or node.get("name")
        description = floor_api.get("details") or node.get("desc")
        visibility = floor_api.get("floor_type") or node.get("type")
        runtime_floor_id = floor_api.get("floor_uid") or node.get("FID")
        floor_category = node.get("floor_cat")

        add_optional_literal(graph, floor_uri, XF.title, title)
        add_optional_literal(graph, floor_uri, XF.description, description)
        add_optional_literal(graph, floor_uri, XF.visibility, visibility)
        add_optional_literal(graph, floor_uri, XF.runtimeFloorId, runtime_floor_id)
        add_optional_literal(graph, floor_uri, XF.floorCategory, floor_category)
        add_optional_literal(graph, floor_uri, XF.phoneNumber, floor_api.get("phone") or node.get("phone"))
        add_optional_literal(graph, floor_uri, XF.emailId, floor_api.get("email") or node.get("email"))

        mapped_floor_curie = floor_category_map.get(floor_category) if isinstance(floor_category, str) else None
        mapped_floor_uri = resolve_curie(mapped_floor_curie, prefix_map) if isinstance(mapped_floor_curie, str) else None
        if mapped_floor_uri is not None:
            graph.add((floor_uri, RDF.type, mapped_floor_uri))

        if parent_uri is not None:
            graph.add((parent_uri, XF.hasChildFloor, floor_uri))
            graph.add((floor_uri, XF.hasParentFloor, parent_uri))

        floor_count += 1

        for child in children:
            if isinstance(child, dict):
                walk(child, parent_uri=floor_uri)

    for child in hierarchy.get("children", []) or []:
        if isinstance(child, dict):
            walk(child, top_under_root=True)

    # export global blocks + attach root
    global_block_ids: set[str] = set()
    for block in global_blocks:
        if not isinstance(block, dict):
            continue
        bid = block.get("block_id")
        if not bid:
            continue
        bid_text = str(bid)
        global_block_ids.add(bid_text)
        block_uri = XF[f"block_{sanitize_fragment(bid_text, 'block')}"]

        graph.add((block_uri, RDF.type, XF.Block))
        graph.add((block_uri, XF.blockId, Literal(bid_text)))
        add_optional_literal(graph, block_uri, XF.title, block.get("title"))
        add_optional_literal(graph, block_uri, XF.blockTypeCode, block.get("type"))

        inherits = parse_flag_to_bool(block.get("display_child_floors"))
        graph.add((block_uri, XF.inheritsToChildFloors, Literal(inherits, datatype=XSD.boolean)))
        graph.add((block_uri, XF.isDerivedBlock, Literal(inherits, datatype=XSD.boolean)))
        graph.add((block_uri, XF.isEditableByLocalOwner, Literal(not inherits, datatype=XSD.boolean)))
        graph.add((block_uri, XF.isDefaultBlock, Literal(parse_flag_to_bool(block.get("default_block")), datatype=XSD.boolean)))
        graph.add((block_uri, XF.isLiveEnabled, Literal(parse_flag_to_bool(block.get("is_live_enabled")), datatype=XSD.boolean)))
        graph.add((block_uri, XF.analyticsEnabled, Literal(parse_flag_to_bool(block.get("analytics_enabled")), datatype=XSD.boolean)))
        graph.add((block_uri, XF.userAllowedToPost, Literal(parse_flag_to_bool(block.get("user_allowed_to_post")), datatype=XSD.boolean)))

        mapped_block_curie = block_title_map.get(block.get("title")) if isinstance(block.get("title"), str) else None
        mapped_block_uri = resolve_curie(mapped_block_curie, prefix_map) if isinstance(mapped_block_curie, str) else None
        if mapped_block_uri is not None:
            graph.add((block_uri, RDF.type, mapped_block_uri))

        if root_hub_uri is not None:
            graph.add((root_hub_uri, XF.hasBlock, block_uri))
            graph.add((root_hub_uri, XF.hasGlobalBlock, block_uri))
            if inherits:
                graph.add((block_uri, XF.originFloor, root_hub_uri))

        block_count += 1

    # export per-floor effective blocks
    for floor_id, floor_data in floor_map.items():
        if not isinstance(floor_data, dict):
            continue
        floor_uri = XF[sanitize_fragment(str(floor_id), "floor")]
        for block in floor_data.get("floor_blocks", []) or []:
            if not isinstance(block, dict):
                continue
            bid = block.get("block_id")
            if not bid:
                continue
            bid_text = str(bid)
            block_uri = XF[f"block_{sanitize_fragment(bid_text, 'block')}"]

            graph.add((block_uri, RDF.type, XF.Block))
            graph.add((block_uri, XF.blockId, Literal(bid_text)))
            add_optional_literal(graph, block_uri, XF.title, block.get("title"))
            add_optional_literal(graph, block_uri, XF.blockTypeCode, block.get("type"))
            graph.add((floor_uri, XF.hasBlock, block_uri))

            title = block.get("title")
            mapped_curie = block_title_map.get(title) if isinstance(title, str) else None
            mapped_uri = resolve_curie(mapped_curie, prefix_map) if isinstance(mapped_curie, str) else None
            if mapped_uri is not None:
                graph.add((block_uri, RDF.type, mapped_uri))

            if bid_text not in global_block_ids:
                graph.add((floor_uri, XF.hasLocalBlock, block_uri))
                if one_local_block_uri is None:
                    one_local_block_uri = block_uri

    return graph, floor_count, block_count, root_hub_uri, one_local_block_uri


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Turtle from ontology export context JSON.")
    parser.add_argument("--context", required=True, help="Path to ontology_export_context.json")
    parser.add_argument("--out", required=True, help="Output Turtle file path")
    args = parser.parse_args()

    context = json.loads(Path(args.context).read_text(encoding="utf-8"))
    graph, floor_count, global_block_count, root_hub_uri, local_block_uri = serialize_context_to_ttl(context)
    graph.serialize(destination=args.out, format="turtle")

    print(f"Exported Turtle: {args.out}")
    print(f"Summary: floors_exported={floor_count}, global_blocks_exported={global_block_count}")
    print("\nExample snippet (one floor + one global block + one local block):")
    print("""@prefix xf: <https://xfloor.ai/ontology#> .

xf:setspr a xf:Floor, xf:HubFloor, xf:Federation .
xf:setspr xf:hasGlobalBlock xf:block_1776142091308 .
xf:setspr_sdc_kan xf:hasLocalBlock xf:block_kan_local_notice .""")

    if root_hub_uri is not None:
        print(f"Root hub: {root_hub_uri}")
    if local_block_uri is not None:
        print(f"Detected local block sample: {local_block_uri}")


if __name__ == "__main__":
    main()
