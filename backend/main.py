from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .llm_utils import LLMResponseError, get_graph_response
from .settings import get_settings

LOGGER = logging.getLogger("backend.main")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


class ChatResponse(BaseModel):
    answer: str
    relevant_node_ids: List[str]
    is_erp_related: bool


class GraphStore:
    def __init__(self) -> None:
        self.graph_json: Dict[str, Any] = {"nodes": [], "links": []}


graph_store = GraphStore()
app = FastAPI(title="Dodge AI ERP Context Graph API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _extract_query_ids(text: str) -> List[str]:
    # Capture practical ERP document-like IDs from user text.
    return sorted(set(re.findall(r"\d+", text)))


def _build_graph_summary(full_graph: Dict[str, Any], query: str) -> Dict[str, Any]:
    nodes = full_graph.get("nodes", [])
    links = full_graph.get("links", [])
    query_ids = _extract_query_ids(query)

    selected_node_ids = set()
    selected_nodes: List[Dict[str, Any]] = []

    def matches(node: Dict[str, Any], token: str) -> bool:
        node_id = str(node.get("id", ""))
        if token in node_id:
            return True

        for field in (
            "salesOrder",
            "deliveryDocument",
            "billingDocument",
            "accountingDocument",
            "customer",
            "businessPartner",
            "product",
            "referenceSdDocument",
            "referenceDocument",
        ):
            value = node.get(field)
            if value is not None and str(value) == token:
                return True
        return False

    if query_ids:
        for node in nodes:
            if any(matches(node, token) for token in query_ids):
                node_id = str(node.get("id", ""))
                if node_id:
                    selected_node_ids.add(node_id)
                    selected_nodes.append(node)

    if not selected_nodes:
        selected_nodes = nodes[:200]
        selected_node_ids = {str(n.get("id", "")) for n in selected_nodes if n.get("id")}

    selected_links: List[Dict[str, Any]] = []
    for edge in links:
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if source in selected_node_ids or target in selected_node_ids:
            selected_links.append(edge)
            if len(selected_links) >= 400:
                break

    return {
        "query_ids": query_ids,
        "graph_stats": {
            "total_nodes": len(nodes),
            "total_links": len(links),
            "selected_nodes": len(selected_nodes),
            "selected_links": len(selected_links),
        },
        "nodes": selected_nodes,
        "links": selected_links,
    }


def _load_graph_json() -> Dict[str, Any]:
    settings = get_settings()
    graph_path = Path(settings.graph_data_path)
    if not graph_path.is_absolute():
        project_root = Path(__file__).resolve().parents[1]
        graph_path = project_root / graph_path

    if not graph_path.exists():
        LOGGER.warning("Graph file not found at %s. API will start with an empty graph.", graph_path)
        return {"nodes": [], "links": []}

    with graph_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError("processed_graph.json must be a JSON object")

    nodes = payload.get("nodes", [])
    links = payload.get("links", [])
    if not isinstance(nodes, list) or not isinstance(links, list):
        raise ValueError("processed_graph.json must contain list fields 'nodes' and 'links'")

    LOGGER.info("Loaded graph into memory with %d nodes and %d links", len(nodes), len(links))
    return payload


@app.on_event("startup")
async def startup_event() -> None:
    setup_logging()
    graph_store.graph_json = _load_graph_json()


@app.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest) -> ChatResponse:
    try:
        graph_summary = _build_graph_summary(graph_store.graph_json, payload.message)
        llm_result = await asyncio.to_thread(get_graph_response, payload.message, graph_summary)
        return ChatResponse(**llm_result)
    except LLMResponseError as exc:
        LOGGER.error("LLM processing error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except TimeoutError as exc:
        LOGGER.error("LLM request timed out: %s", exc)
        raise HTTPException(status_code=504, detail="LLM request timed out") from exc
    except ValueError as exc:
        LOGGER.error("Malformed LLM output: %s", exc)
        raise HTTPException(status_code=502, detail="LLM returned malformed JSON") from exc
    except Exception as exc:  # pragma: no cover - defensive for prototype runtime
        LOGGER.exception("Unexpected /api/chat failure")
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "nodes_loaded": len(graph_store.graph_json.get("nodes", [])),
        "links_loaded": len(graph_store.graph_json.get("links", [])),
    }
