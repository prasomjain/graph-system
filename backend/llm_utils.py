from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List

from .settings import get_settings

LOGGER = logging.getLogger("llm_utils")

STRICT_RESPONSE_MESSAGE = "This system is designed for ERP data analysis only."


class LLMResponseError(RuntimeError):
    pass


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def _validate_response_shape(payload: Dict[str, Any]) -> Dict[str, Any]:
    answer = payload.get("answer")
    node_ids = payload.get("relevant_node_ids")
    is_erp_related = payload.get("is_erp_related")

    if not isinstance(answer, str):
        raise LLMResponseError("Field 'answer' must be a string")
    if not isinstance(node_ids, list) or any(not isinstance(x, str) for x in node_ids):
        raise LLMResponseError("Field 'relevant_node_ids' must be a list of strings")
    if not isinstance(is_erp_related, bool):
        raise LLMResponseError("Field 'is_erp_related' must be a boolean")

    if not is_erp_related:
        payload["answer"] = STRICT_RESPONSE_MESSAGE
        payload["relevant_node_ids"] = []

    return {
        "answer": payload["answer"],
        "relevant_node_ids": payload["relevant_node_ids"],
        "is_erp_related": payload["is_erp_related"],
    }


def _build_system_prompt() -> str:
    return (
        "You are an ERP Data Expert. "
        "You have a graph with nodes (SalesOrder, Delivery, Invoice, Payment, Customer, Product) "
        "and edges (SHIPPED_IN, BILLED_TO, PAID_BY). "
        "Your job is to identify the IDs mentioned in the query (e.g., 'Order #123') and find the path to related documents. "
        "Use only the provided graph context. Do not invent nodes, edges, or IDs. "
        "If the question is off-topic or not ERP-related, set is_erp_related to false and use answer exactly: "
        f"'{STRICT_RESPONSE_MESSAGE}'. "
        "Always return valid JSON only with keys: answer, relevant_node_ids, is_erp_related."
    )


def _build_user_prompt(user_query: str, graph_json: Dict[str, Any]) -> str:
    return json.dumps(
        {
            "query": user_query,
            "graph_context": graph_json,
            "few_shot_examples": [
                {
                    "input": "Trace Sales Order #740506",
                    "output": {
                        "answer": "Sales Order 740506 is linked to downstream delivery and billing documents in the graph.",
                        "relevant_node_ids": [
                            "sales_order_headers:740506",
                            "outbound_delivery_headers:80738076",
                            "billing_document_headers:90504298",
                        ],
                        "is_erp_related": True,
                    },
                },
                {
                    "input": "How do I make a chocolate cake?",
                    "output": {
                        "answer": STRICT_RESPONSE_MESSAGE,
                        "relevant_node_ids": [],
                        "is_erp_related": False,
                    },
                },
            ],
            "output_schema": {
                "answer": "string",
                "relevant_node_ids": ["string"],
                "is_erp_related": True,
            },
        },
        ensure_ascii=False,
    )


def _call_openrouter(system_prompt: str, user_prompt: str) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LLMResponseError("openai is not installed") from exc

    settings = get_settings()
    if not settings.openrouter_api_key:
        raise LLMResponseError("OPENROUTER_API_KEY is missing in .env")

    client = OpenAI(
        api_key=settings.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
    )

    try:
        response = client.chat.completions.create(
            model=settings.openrouter_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            timeout=settings.llm_timeout_seconds,
        )
    except Exception as exc:
        message = str(exc)
        if "timeout" in exc.__class__.__name__.lower() or "deadline" in exc.__class__.__name__.lower():
            raise TimeoutError("OpenRouter request timed out") from exc
        if "not found" in message.lower() and "model" in message.lower():
            raise LLMResponseError(
                "OpenRouter model not found or unsupported. "
                "Update OPENROUTER_MODEL in .env (for example: openai/gpt-3.5-turbo) and retry."
            ) from exc
        raise LLMResponseError(f"OpenRouter request failed: {exc}") from exc

    text = response.choices[0].message.content
    if not text:
        raise LLMResponseError("OpenRouter returned an empty response")
    return text


def get_graph_response(user_query: str, graph_json: Dict[str, Any]) -> Dict[str, Any]:
    """Return a strict JSON response grounded in the provided graph context."""
    system_prompt = _build_system_prompt()
    user_prompt = _build_user_prompt(user_query=user_query, graph_json=graph_json)
    LOGGER.info("Calling LLM provider=openrouter")
    raw = _call_openrouter(system_prompt, user_prompt)

    try:
        parsed = json.loads(_strip_code_fences(raw))
    except json.JSONDecodeError as exc:
        LOGGER.error("LLM returned malformed JSON: %s", raw)
        raise ValueError("LLM returned malformed JSON") from exc

    return _validate_response_shape(parsed)
