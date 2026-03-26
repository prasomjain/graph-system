from __future__ import annotations


def _status_label(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def print_readiness_report(
    data_ingestion_passed: bool,
    llm_guardrails_passed: bool,
    graph_connectivity_passed: bool,
) -> None:
    report = (
        f"[{_status_label(data_ingestion_passed)}] Data Ingestion | "
        f"[{_status_label(llm_guardrails_passed)}] LLM Guardrails | "
        f"[{_status_label(graph_connectivity_passed)}] Graph Connectivity"
    )
    print(report)
