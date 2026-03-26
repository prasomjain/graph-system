from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from backend.ingest_jsonl import run_ingestion


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _graph_path() -> Path:
    return _project_root() / "frontend" / "src" / "assets" / "processed_graph.json"


def _data_dir() -> Path:
    return _project_root() / "data"


def _count_jsonl_rows(data_dir: Path) -> int:
    total = 0
    for file_path in data_dir.rglob("*.jsonl"):
        with file_path.open("r", encoding="utf-8") as handle:
            total += sum(1 for line in handle if line.strip())
    return total


def _load_graph() -> Dict[str, Any]:
    graph_file = _graph_path()
    assert graph_file.exists(), f"Missing graph file: {graph_file}"
    with graph_file.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _node_entity(node: Dict[str, Any]) -> str:
    return str(node.get("entity_type", ""))


def _node_id(node: Dict[str, Any]) -> str:
    return str(node.get("id", ""))


def test_node_count_matches_total_jsonl_lines() -> None:
    run_ingestion()
    graph = _load_graph()
    total_rows = _count_jsonl_rows(_data_dir())
    assert len(graph["nodes"]) == total_rows


def test_invoices_are_connected_to_order_or_delivery() -> None:
    run_ingestion()
    graph = _load_graph()

    nodes: List[Dict[str, Any]] = graph["nodes"]
    links: List[Dict[str, Any]] = graph["links"]

    node_map = {_node_id(n): n for n in nodes if _node_id(n)}

    adjacency: Dict[str, set[str]] = {node_id: set() for node_id in node_map}
    for link in links:
        source = str(link.get("source", ""))
        target = str(link.get("target", ""))
        if source in adjacency:
            adjacency[source].add(target)
        if target in adjacency:
            adjacency[target].add(source)

    invoice_nodes = [n for n in nodes if _node_entity(n) == "billing_document_headers"]
    assert invoice_nodes, "No invoice header nodes found in graph"

    broken_invoice_ids: List[str] = []
    for invoice in invoice_nodes:
        inv_id = _node_id(invoice)
        neighbors = adjacency.get(inv_id, set())

        is_connected = False
        for neighbor_id in neighbors:
            neighbor = node_map.get(neighbor_id, {})
            neighbor_type = _node_entity(neighbor)
            if neighbor_type in {"sales_order_headers", "outbound_delivery_headers"}:
                is_connected = True
                break

        if not is_connected:
            broken_invoice_ids.append(inv_id)

    assert not broken_invoice_ids, f"Broken invoice flow nodes: {broken_invoice_ids[:20]}"


def test_numeric_properties_are_not_strings() -> None:
    run_ingestion()
    graph = _load_graph()

    numeric_fields = {
        "totalNetAmount",
        "netAmount",
        "billingQuantity",
        "actualDeliveryQuantity",
        "requestedQuantity",
        "amountInTransactionCurrency",
        "amountInCompanyCodeCurrency",
        "grossWeight",
        "netWeight",
    }

    seen_numeric_values = 0
    for node in graph["nodes"]:
        for field in numeric_fields:
            if field not in node:
                continue
            value = node[field]
            if isinstance(value, (int, float)):
                seen_numeric_values += 1
                continue
            raise AssertionError(
                f"Field '{field}' is not numeric on node '{node.get('id', '')}': {value!r}"
            )

    assert seen_numeric_values > 0, "No numeric fields were validated"
