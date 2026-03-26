from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, DefaultDict, Dict, Iterable, List, Set, Tuple

import networkx as nx

LOGGER = logging.getLogger("ingest_jsonl")


@dataclass(frozen=True)
class NodeRecord:
    node_id: str
    entity_type: str
    payload: Dict[str, Any]


EntityFieldIndex = DefaultDict[Tuple[str, str], DefaultDict[str, Set[str]]]

NUMERIC_FIELDS: Set[str] = {
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


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def discover_jsonl_files(data_dir: Path) -> List[Path]:
    files = sorted(data_dir.rglob("*.jsonl"))
    LOGGER.info("Discovered %d JSONL files under %s", len(files), data_dir)
    return files


def safe_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def candidate_node_keys(entity_type: str) -> List[str]:
    by_entity: Dict[str, List[str]] = {
        "sales_order_headers": ["salesOrder"],
        "sales_order_items": ["salesOrder", "salesOrderItem"],
        "outbound_delivery_headers": ["deliveryDocument"],
        "outbound_delivery_items": ["deliveryDocument", "deliveryDocumentItem"],
        "billing_document_headers": ["billingDocument"],
        "billing_document_items": ["billingDocument", "billingDocumentItem"],
        "payments_accounts_receivable": ["accountingDocument", "accountingDocumentItem"],
        "journal_entry_items_accounts_receivable": ["accountingDocument", "accountingDocumentItem"],
        "business_partners": ["customer", "businessPartner"],
        "products": ["product"],
    }
    fallback_keys = [
        "id",
        "ID",
        "salesOrder",
        "deliveryDocument",
        "billingDocument",
        "accountingDocument",
        "customer",
        "businessPartner",
        "product",
    ]
    return by_entity.get(entity_type, fallback_keys)


def make_node_id(entity_type: str, payload: Dict[str, Any], source_tag: str) -> str:
    keys = candidate_node_keys(entity_type)
    parts: List[str] = []
    for key in keys:
        value = safe_text(payload.get(key))
        if value:
            parts.append(value)
    if parts:
        return f"{entity_type}:{'|'.join(parts)}"
    return f"{entity_type}:row:{source_tag}"


def parse_jsonl_file(file_path: Path) -> Iterable[Tuple[int, Dict[str, Any]]]:
    with file_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                LOGGER.warning(
                    "Skipping invalid JSON in %s line %d: %s",
                    file_path,
                    line_number,
                    exc,
                )
                continue
            if not isinstance(payload, dict):
                LOGGER.warning(
                    "Skipping non-object JSON in %s line %d",
                    file_path,
                    line_number,
                )
                continue
            yield line_number, payload


def _coerce_numeric(value: str) -> Any:
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def normalize_payload_types(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, str) and key in NUMERIC_FIELDS:
            normalized[key] = _coerce_numeric(value)
            continue
        normalized[key] = value
    return normalized


def add_index_values(
    index: EntityFieldIndex,
    entity_type: str,
    node_id: str,
    payload: Dict[str, Any],
) -> None:
    for field, value in payload.items():
        text = safe_text(value)
        if not text:
            continue
        index[(entity_type, field)][text].add(node_id)


def ingest_nodes(data_dir: Path) -> Tuple[nx.DiGraph, List[NodeRecord], EntityFieldIndex]:
    graph = nx.DiGraph()
    records: List[NodeRecord] = []
    index: EntityFieldIndex = defaultdict(lambda: defaultdict(set))

    seen_node_ids: Dict[str, int] = defaultdict(int)

    for file_path in discover_jsonl_files(data_dir):
        entity_type = file_path.parent.name
        for line_number, payload in parse_jsonl_file(file_path):
            payload = normalize_payload_types(payload)
            source_tag = f"{file_path.name}:{line_number}"
            node_id = make_node_id(entity_type, payload, source_tag)

            # Keep every JSONL line as a node, even if business keys collide.
            if node_id in graph:
                seen_node_ids[node_id] += 1
                node_id = f"{node_id}#dup{seen_node_ids[node_id]}"

            node_attrs: Dict[str, Any] = {
                "entity_type": entity_type,
                "source_file": str(file_path.relative_to(data_dir.parent)),
                "source_line": line_number,
                **payload,
            }
            graph.add_node(node_id, **node_attrs)
            add_index_values(index, entity_type, node_id, payload)
            records.append(NodeRecord(node_id=node_id, entity_type=entity_type, payload=payload))

    LOGGER.info("Ingested %d nodes", graph.number_of_nodes())
    return graph, records, index


def add_edge_safe(
    graph: nx.DiGraph,
    source: str,
    target: str,
    relation: str,
    evidence: Dict[str, Any],
) -> None:
    if not source or not target:
        return
    graph.add_edge(source, target, relation=relation, evidence=evidence)


def get_nodes(
    index: EntityFieldIndex,
    entity_type: str,
    field: str,
    value: Any,
) -> Set[str]:
    text = safe_text(value)
    if not text:
        return set()
    return set(index[(entity_type, field)].get(text, set()))


def link_order_to_delivery(
    graph: nx.DiGraph,
    records: List[NodeRecord],
    index: EntityFieldIndex,
) -> int:
    edge_count_before = graph.number_of_edges()
    for row in records:
        if row.entity_type != "outbound_delivery_items":
            continue

        sales_order_id = safe_text(row.payload.get("referenceSdDocument"))
        delivery_id = safe_text(row.payload.get("deliveryDocument"))

        if not sales_order_id or not delivery_id:
            continue

        order_nodes = get_nodes(index, "sales_order_headers", "salesOrder", sales_order_id)
        delivery_nodes = get_nodes(index, "outbound_delivery_headers", "deliveryDocument", delivery_id)

        for order_node in order_nodes:
            for delivery_node in delivery_nodes:
                add_edge_safe(
                    graph,
                    order_node,
                    delivery_node,
                    relation="order_to_delivery",
                    evidence={
                        "sales_order_id": sales_order_id,
                        "delivery_id": delivery_id,
                        "bridge": row.node_id,
                    },
                )

    return graph.number_of_edges() - edge_count_before


def link_delivery_to_invoice(
    graph: nx.DiGraph,
    records: List[NodeRecord],
    index: EntityFieldIndex,
) -> int:
    edge_count_before = graph.number_of_edges()
    for row in records:
        if row.entity_type != "billing_document_items":
            continue

        delivery_id = safe_text(row.payload.get("referenceSdDocument"))
        billing_doc_id = safe_text(row.payload.get("billingDocument"))

        if not delivery_id or not billing_doc_id:
            continue

        delivery_nodes = get_nodes(index, "outbound_delivery_headers", "deliveryDocument", delivery_id)
        invoice_nodes = get_nodes(index, "billing_document_headers", "billingDocument", billing_doc_id)

        for delivery_node in delivery_nodes:
            for invoice_node in invoice_nodes:
                add_edge_safe(
                    graph,
                    delivery_node,
                    invoice_node,
                    relation="delivery_to_invoice",
                    evidence={
                        "delivery_id": delivery_id,
                        "billing_doc_id": billing_doc_id,
                        "bridge": row.node_id,
                    },
                )

    return graph.number_of_edges() - edge_count_before


def link_invoice_to_payment(
    graph: nx.DiGraph,
    records: List[NodeRecord],
    index: EntityFieldIndex,
) -> int:
    edge_count_before = graph.number_of_edges()

    # Direct link path when payment record has invoice reference.
    for row in records:
        if row.entity_type != "payments_accounts_receivable":
            continue

        payment_nodes = {row.node_id}
        invoice_ref = safe_text(row.payload.get("invoiceReference"))
        if invoice_ref:
            invoice_nodes = get_nodes(index, "billing_document_headers", "billingDocument", invoice_ref)
            invoice_nodes |= get_nodes(index, "billing_document_headers", "accountingDocument", invoice_ref)
            for invoice_node in invoice_nodes:
                for payment_node in payment_nodes:
                    add_edge_safe(
                        graph,
                        invoice_node,
                        payment_node,
                        relation="invoice_to_payment",
                        evidence={"invoice_id": invoice_ref, "strategy": "direct_invoice_reference"},
                    )

    # Bridge through journal entries when payment rows only carry accountingDocument.
    for row in records:
        if row.entity_type != "journal_entry_items_accounts_receivable":
            continue

        invoice_id = safe_text(row.payload.get("referenceDocument"))
        payment_accounting_doc = safe_text(row.payload.get("accountingDocument"))
        if not invoice_id or not payment_accounting_doc:
            continue

        invoice_nodes = get_nodes(index, "billing_document_headers", "billingDocument", invoice_id)
        payment_nodes = get_nodes(
            index,
            "payments_accounts_receivable",
            "accountingDocument",
            payment_accounting_doc,
        )

        for invoice_node in invoice_nodes:
            for payment_node in payment_nodes:
                add_edge_safe(
                    graph,
                    invoice_node,
                    payment_node,
                    relation="invoice_to_payment",
                    evidence={
                        "invoice_id": invoice_id,
                        "payment_accounting_document": payment_accounting_doc,
                        "strategy": "journal_entry_bridge",
                        "bridge": row.node_id,
                    },
                )

    return graph.number_of_edges() - edge_count_before


def link_customers_to_transactions(
    graph: nx.DiGraph,
    records: List[NodeRecord],
    index: EntityFieldIndex,
) -> int:
    edge_count_before = graph.number_of_edges()

    customer_nodes_by_id: DefaultDict[str, Set[str]] = defaultdict(set)
    customer_nodes_by_id.update(index[("business_partners", "customer")])
    for customer_id, nodes in index[("business_partners", "businessPartner")].items():
        customer_nodes_by_id[customer_id].update(nodes)

    transaction_customer_fields: Dict[str, List[str]] = {
        "sales_order_headers": ["soldToParty"],
        "billing_document_headers": ["soldToParty"],
        "payments_accounts_receivable": ["customer"],
        "journal_entry_items_accounts_receivable": ["customer"],
    }

    for row in records:
        fields = transaction_customer_fields.get(row.entity_type)
        if not fields:
            continue

        for field in fields:
            customer_id = safe_text(row.payload.get(field))
            if not customer_id:
                continue

            for customer_node in customer_nodes_by_id.get(customer_id, set()):
                add_edge_safe(
                    graph,
                    customer_node,
                    row.node_id,
                    relation="customer_to_transaction",
                    evidence={"customer_id": customer_id, "field": field},
                )

    return graph.number_of_edges() - edge_count_before


def link_products_to_transactions(
    graph: nx.DiGraph,
    records: List[NodeRecord],
    index: EntityFieldIndex,
) -> int:
    edge_count_before = graph.number_of_edges()

    product_nodes_by_id: Dict[str, Set[str]] = dict(index[("products", "product")])
    transaction_product_fields: Dict[str, List[str]] = {
        "sales_order_items": ["material"],
        "billing_document_items": ["material"],
    }

    for row in records:
        fields = transaction_product_fields.get(row.entity_type)
        if not fields:
            continue

        for field in fields:
            product_id = safe_text(row.payload.get(field))
            if not product_id:
                continue

            for product_node in product_nodes_by_id.get(product_id, set()):
                add_edge_safe(
                    graph,
                    product_node,
                    row.node_id,
                    relation="product_to_transaction",
                    evidence={"product_id": product_id, "field": field},
                )

    return graph.number_of_edges() - edge_count_before


def build_relationships(graph: nx.DiGraph, records: List[NodeRecord], index: EntityFieldIndex) -> None:
    LOGGER.info("Building graph relationships...")
    order_delivery_edges = link_order_to_delivery(graph, records, index)
    delivery_invoice_edges = link_delivery_to_invoice(graph, records, index)
    invoice_payment_edges = link_invoice_to_payment(graph, records, index)
    customer_edges = link_customers_to_transactions(graph, records, index)
    product_edges = link_products_to_transactions(graph, records, index)

    LOGGER.info(
        "Edge build summary | order->delivery=%d | delivery->invoice=%d | invoice->payment=%d | customer->tx=%d | product->tx=%d",
        order_delivery_edges,
        delivery_invoice_edges,
        invoice_payment_edges,
        customer_edges,
        product_edges,
    )


def graph_health(graph: nx.DiGraph) -> Dict[str, int]:
    orphaned_nodes = sum(1 for node in graph.nodes if graph.degree(node) == 0)
    health = {
        "total_nodes": graph.number_of_nodes(),
        "total_edges": graph.number_of_edges(),
        "orphaned_nodes": orphaned_nodes,
    }
    LOGGER.info("Graph Health: %s", health)
    print(f"Graph Health: {health}")
    return health


def export_graph(graph: nx.DiGraph, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    nodes: List[Dict[str, Any]] = []
    for node_id, attrs in graph.nodes(data=True):
        node_obj = {"id": node_id}
        node_obj.update(attrs)
        nodes.append(node_obj)

    links: List[Dict[str, Any]] = []
    for source, target, attrs in graph.edges(data=True):
        link_obj = {"source": source, "target": target}
        link_obj.update(attrs)
        links.append(link_obj)

    payload = {"nodes": nodes, "links": links}
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)

    LOGGER.info("Exported graph JSON to %s", output_path)


def run_ingestion() -> None:
    project_root = Path(__file__).resolve().parents[1]
    data_dir = project_root / "data"
    output_path = project_root / "frontend" / "src" / "assets" / "processed_graph.json"

    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    graph, records, index = ingest_nodes(data_dir)
    build_relationships(graph, records, index)
    graph_health(graph)
    export_graph(graph, output_path)


def main() -> None:
    setup_logging()
    run_ingestion()


if __name__ == "__main__":
    main()
