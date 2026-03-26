from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "http://localhost:8000/api/chat"
REQUEST_BODY = {"message": "Trace Sales Order #101"}


def load_graph_node_ids() -> set[str]:
    root = Path(__file__).resolve().parents[1]
    graph_path = root / "frontend" / "src" / "assets" / "processed_graph.json"
    with graph_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    node_ids: set[str] = set()
    for node in payload.get("nodes", []):
        node_id = node.get("id")
        if node_id is not None:
            node_ids.add(str(node_id))
    return node_ids


def post_chat() -> tuple[int, dict]:
    payload = json.dumps(REQUEST_BODY).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status = response.getcode()
            raw = response.read().decode("utf-8")
            return status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connection error: {exc}") from exc


def main() -> int:
    graph_ids = load_graph_node_ids()
    status_code, response_json = post_chat()

    if status_code != 200:
        print(f"FAIL: expected status 200, got {status_code}")
        return 1

    answer = response_json.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        print("FAIL: answer is missing or empty")
        return 1

    relevant_node_ids = response_json.get("relevant_node_ids")
    if not isinstance(relevant_node_ids, list):
        print("FAIL: relevant_node_ids must be a list")
        return 1

    unknown_ids = [node_id for node_id in relevant_node_ids if str(node_id) not in graph_ids]
    if unknown_ids:
        print(f"FAIL: relevant_node_ids not found in processed_graph.json: {unknown_ids[:10]}")
        return 1

    print("BACKEND VERIFIED")
    print(json.dumps(response_json, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
