# ai/tests/test_check_pipeline.py
"""Checks that the pipeline diagnostic distinguishes completion from review readiness."""

from collections import Counter

from ai.schema import FlagSeverity
from ai.scripts.check_pipeline import _completion_message


def test_completion_message_reports_review_without_marking_the_pipeline_degraded() -> None:
    severity = Counter({FlagSeverity.SERIOUS: 1, FlagSeverity.WARN: 2})

    assert _completion_message(False, severity) == "COMPLETED — REVIEW REQUIRED"
    assert _completion_message(True, severity).startswith("DEGRADED")
    assert _completion_message(False, Counter()) == "OK"
