from __future__ import annotations

from typing import Any, Dict

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app, graph_store


@pytest.fixture()
def mock_graph() -> Dict[str, Any]:
    return {
        "nodes": [
            {"id": "sales_order_headers:101", "entity_type": "sales_order_headers", "salesOrder": "101"},
            {
                "id": "outbound_delivery_headers:501",
                "entity_type": "outbound_delivery_headers",
                "deliveryDocument": "501",
            },
        ],
        "links": [
            {
                "source": "sales_order_headers:101",
                "target": "outbound_delivery_headers:501",
                "relation": "order_to_delivery",
            }
        ],
    }


@pytest.fixture()
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    def _stub_response(user_query: str, graph_json: Dict[str, Any]) -> Dict[str, Any]:
        lowered = user_query.lower()
        if "capital of france" in lowered:
            return {
                "answer": "This system is designed for ERP data analysis only.",
                "relevant_node_ids": [],
                "is_erp_related": False,
            }

        return {
            "answer": "Order 101 is linked to delivery 501.",
            "relevant_node_ids": ["sales_order_headers:101", "outbound_delivery_headers:501"],
            "is_erp_related": True,
        }

    monkeypatch.setattr("backend.main.get_graph_response", _stub_response)


@pytest.mark.asyncio
async def test_chat_endpoint_positive_query(mock_graph: Dict[str, Any], fake_llm: None) -> None:
    graph_store.graph_json = mock_graph
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:  # type: ignore[arg-type]
        response = await client.post("/api/chat", json={"message": "Status of Order 101"})
        assert response.status_code == 200

        payload = response.json()
        assert payload["is_erp_related"] is True
        assert payload["relevant_node_ids"]


@pytest.mark.asyncio
async def test_chat_endpoint_guardrail_off_topic(mock_graph: Dict[str, Any], fake_llm: None) -> None:
    graph_store.graph_json = mock_graph
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:  # type: ignore[arg-type]
        response = await client.post("/api/chat", json={"message": "What is the capital of France?"})
        assert response.status_code == 200

        payload = response.json()
        assert payload["is_erp_related"] is False
        assert payload["answer"] == "This system is designed for ERP data analysis only."


@pytest.mark.asyncio
async def test_chat_endpoint_empty_message(mock_graph: Dict[str, Any], fake_llm: None) -> None:
    graph_store.graph_json = mock_graph
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:  # type: ignore[arg-type]
        response = await client.post("/api/chat", json={"message": ""})
        assert response.status_code == 422

        payload = response.json()
        assert "detail" in payload
