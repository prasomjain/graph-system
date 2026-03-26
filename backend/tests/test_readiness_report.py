from __future__ import annotations

from backend.tests.readiness_report import print_readiness_report


def test_readiness_report_output(capsys) -> None:
    print_readiness_report(True, True, True)
    captured = capsys.readouterr()
    assert (
        captured.out.strip()
        == "[PASS] Data Ingestion | [PASS] LLM Guardrails | [PASS] Graph Connectivity"
    )
