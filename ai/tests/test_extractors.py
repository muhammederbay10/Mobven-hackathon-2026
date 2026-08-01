# ai/tests/test_extractors.py
"""Offline extractor tests use hand-authored model stand-ins and never call OpenAI."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from ai.chunker import Chunk
from ai.extractors import ExtractorConfigurationError, _default_caller, extract_chunks
from ai.prompts import appointments, rules, specimens
from ai.schema import (
    AppointmentsAgentOutput,
    ExtractorRole,
    ExtractorStatus,
    ProgressState,
    RulesAgentOutput,
    SpecimensAgentOutput,
)


EMPTY_APPOINTMENTS = json.dumps(
    {
        "company": {
            "legal_name": "ACME ANONİM ŞİRKETİ",
            "vkn": None,
            "trade_registry_no": None,
            "mersis": None,
            "address": None,
            "evidence": [{"page": 1, "quote": "ACME ANONİM ŞİRKETİ"}],
        },
        "notary": None,
        "document_valid_until": None,
        "appointments": [],
        "references": [],
    },
    ensure_ascii=False,
)
EMPTY_RULES = json.dumps({"rules": []})
EMPTY_SPECIMENS = json.dumps({"specimens": []})


def chunk(agent: str, number: int = 1, *, supporting_only: bool = False) -> Chunk:
    return Chunk(
        chunk_id=f"{agent}_p{number}",
        agent=agent,  # type: ignore[arg-type]
        pages=[number],
        images=[f"extract-image-{number}".encode()],
        context_header=f"Context for absolute page {number}",
        supporting_only=supporting_only,
    )


def response_for(agent: str) -> str:
    return {
        "appointments": EMPTY_APPOINTMENTS,
        "rules": EMPTY_RULES,
        "annex": EMPTY_RULES,
        "specimens": EMPTY_SPECIMENS,
    }[agent]


def run(coroutine):
    return asyncio.run(coroutine)


def test_extracts_each_primary_shape_and_preserves_verbatim_fields() -> None:
    appointment_payload = json.loads(EMPTY_APPOINTMENTS)
    appointment_payload["document_valid_until"] = "2030-12-31"
    appointment_payload["appointments"] = [
        {
            "name_printed": "ALİ YILMAZ",
            "title": "Müdür",
            "id_no_masked": "123******45",
            "group_code": "A",
            "authority_form": "müştereken",
            "joint_with_names": ["AYŞE ÖZTÜRK"],
            "valid_from": None,
            "valid_until": "2028-05-01",
            "evidence": {"page": 1, "quote": "ALİ YILMAZ ve AYŞE ÖZTÜRK müştereken"},
        }
    ]
    payloads = {
        "appointments": json.dumps(appointment_payload, ensure_ascii=False),
        "rules": EMPTY_RULES,
        "specimens": EMPTY_SPECIMENS,
    }

    async def caller(part, role, model, system_prompt, content):
        return payloads[part.agent]

    results = run(
        extract_chunks(
            [chunk("appointments"), chunk("rules", 2), chunk("specimens", 3)],
            call_model=caller,
            extraction_model="reader-test",
            witness_model="",
        )
    )

    assert isinstance(results[0].output, AppointmentsAgentOutput)
    assert results[0].output.appointments[0].evidence.quote == (
        "ALİ YILMAZ ve AYŞE ÖZTÜRK müştereken"
    )
    assert str(results[0].output.appointments[0].valid_until) == "2028-05-01"
    assert isinstance(results[1].output, RulesAgentOutput)
    assert isinstance(results[2].output, SpecimensAgentOutput)


def test_witness_runs_only_for_primary_rule_chunks_in_deterministic_order() -> None:
    calls: list[tuple[str, ExtractorRole, str]] = []
    witness_instructions: list[str] = []

    async def caller(part, role, model, system_prompt, content):
        calls.append((part.chunk_id, role, model))
        if role is ExtractorRole.WITNESS:
            witness_instructions.append(content[0]["text"])
        return response_for(part.agent)

    results = run(
        extract_chunks(
            [chunk("appointments"), chunk("rules", 2), chunk("annex", 3, supporting_only=True)],
            call_model=caller,
            extraction_model="reader-test",
            witness_model="witness-test",
        )
    )

    assert [(result.chunk_id, result.role) for result in results] == [
        ("appointments_p1", ExtractorRole.PRIMARY),
        ("rules_p2", ExtractorRole.PRIMARY),
        ("rules_p2", ExtractorRole.WITNESS),
        ("annex_p3", ExtractorRole.PRIMARY),
    ]
    assert calls.count(("rules_p2", ExtractorRole.WITNESS, "witness-test")) == 1
    assert "bağımsız ikinci okumadır" in witness_instructions[0]
    assert not any(item[0] == "annex_p3" and item[1] is ExtractorRole.WITNESS for item in calls)
    assert isinstance(results[-1].output, RulesAgentOutput)
    assert results[-1].supporting_only is True


def test_empty_witness_disables_second_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WITNESS_MODEL", "configured-witness")
    calls = 0

    async def caller(part, role, model, system_prompt, content):
        nonlocal calls
        calls += 1
        return EMPTY_RULES

    results = run(
        extract_chunks(
            [chunk("rules")],
            call_model=caller,
            extraction_model="reader-test",
            witness_model="",
        )
    )

    assert calls == 1
    assert len(results) == 1
    assert results[0].role is ExtractorRole.PRIMARY


def test_max_concurrency_bounds_simultaneous_model_calls() -> None:
    active = 0
    observed_max = 0

    async def caller(part, role, model, system_prompt, content):
        nonlocal active, observed_max
        active += 1
        observed_max = max(observed_max, active)
        await asyncio.sleep(0.01)
        active -= 1
        return EMPTY_RULES

    results = run(
        extract_chunks(
            [chunk("rules", page) for page in range(1, 7)],
            call_model=caller,
            extraction_model="reader-test",
            witness_model="",
            max_concurrency=2,
        )
    )

    assert observed_max == 2
    assert all(result.status is ExtractorStatus.SUCCESS for result in results)


def test_invalid_json_retries_once_with_validation_feedback() -> None:
    instructions: list[str] = []
    replies = iter(["not-json", EMPTY_RULES])

    async def caller(part, role, model, system_prompt, content):
        instructions.append(content[0]["text"])
        return next(replies)

    result = run(
        extract_chunks(
            [chunk("rules")],
            call_model=caller,
            extraction_model="reader-test",
            witness_model="",
        )
    )[0]

    assert result.status is ExtractorStatus.SUCCESS
    assert result.attempts == 2
    assert result.raw_responses == ["not-json", EMPTY_RULES]
    assert "invalid JSON" in instructions[1]
    assert "DÜZELTİLMİŞ JSON" in instructions[1]


def test_two_failures_return_chunk_failed_without_cancelling_siblings() -> None:
    attempts: dict[str, int] = {}

    async def caller(part, role, model, system_prompt, content):
        attempts[part.chunk_id] = attempts.get(part.chunk_id, 0) + 1
        if part.chunk_id == "rules_p1":
            raise TimeoutError("model timed out")
        return EMPTY_SPECIMENS

    failed, successful = run(
        extract_chunks(
            [chunk("rules"), chunk("specimens", 2)],
            call_model=caller,
            extraction_model="reader-test",
            witness_model="",
        )
    )

    assert failed.status is ExtractorStatus.FAILED
    assert failed.chunk_failed is True
    assert failed.attempts == 2
    assert failed.chunk_id == "rules_p1"
    assert "TimeoutError" in failed.error
    assert successful.status is ExtractorStatus.SUCCESS
    assert attempts == {"rules_p1": 2, "specimens_p2": 1}


def test_progress_reports_start_completion_failure_and_review_skip() -> None:
    events = []

    def progress(event):
        events.append(event)

    async def caller(part, role, model, system_prompt, content):
        if part.agent == "rules":
            return "{"
        return EMPTY_SPECIMENS

    results = run(
        extract_chunks(
            [chunk("specimens"), chunk("rules", 2), chunk("review", 3, supporting_only=True)],
            call_model=caller,
            extraction_model="reader-test",
            witness_model="",
            progress=progress,
        )
    )

    assert [event.state for event in events].count(ProgressState.RUNNING) == 2
    assert any(event.state is ProgressState.DONE for event in events)
    assert any(event.state is ProgressState.FAILED for event in events)
    assert any(event.state is ProgressState.SKIPPED for event in events)
    assert results[-1].status is ExtractorStatus.SKIPPED
    assert results[-1].attempts == 0


def test_content_uses_absolute_page_labels_and_extract_images() -> None:
    captured = None
    part = Chunk(
        chunk_id="rules_p4-5",
        agent="rules",
        pages=[4, 5],
        images=[b"high-four", b"high-five"],
        context_header="absolute context",
        supporting_only=False,
    )

    async def caller(chunk_value, role, model, system_prompt, content):
        nonlocal captured
        captured = content
        return EMPTY_RULES

    run(
        extract_chunks(
            [part],
            call_model=caller,
            extraction_model="reader-test",
            witness_model="",
        )
    )

    assert captured[1]["text"] == "Mutlak sayfa 4"
    assert captured[3]["text"] == "Mutlak sayfa 5"
    assert captured[2]["image_url"]["url"].endswith("aGlnaC1mb3Vy")
    assert captured[4]["image_url"]["detail"] == "high"


def test_configuration_errors_are_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXTRACTION_MODEL", raising=False)
    with pytest.raises(ExtractorConfigurationError, match="EXTRACTION_MODEL"):
        run(extract_chunks([], witness_model=""))

    with pytest.raises(ExtractorConfigurationError, match="max_concurrency"):
        run(
            extract_chunks(
                [], extraction_model="reader-test", witness_model="", max_concurrency=0
            )
        )


def test_default_openai_call_omits_unsupported_temperature(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            recorded.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=EMPTY_RULES))]
            )

    class FakeClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setattr("openai.AsyncOpenAI", FakeClient)
    raw = run(
        _default_caller(
            chunk("rules"),
            ExtractorRole.PRIMARY,
            "reader-test",
            "system",
            [{"type": "text", "text": "user"}],
        )
    )

    assert raw == EMPTY_RULES
    assert recorded["model"] == "reader-test"
    assert recorded["response_format"] == {"type": "json_object"}
    assert "temperature" not in recorded


def test_turkish_prompts_keep_anti_hallucination_requirements() -> None:
    combined = "\n".join(
        [appointments.SYSTEM_PROMPT, rules.SYSTEM_PROMPT, specimens.SYSTEM_PROMPT]
    )
    assert "HARFİ HARFİNE" in combined
    assert "UNREADABLE" in combined
    assert "joint_with" in appointments.SYSTEM_PROMPT
    assert "valid_until" in appointments.SYSTEM_PROMPT
    assert "joint_with" in rules.SYSTEM_PROMPT
    assert "valid_until" in rules.SYSTEM_PROMPT
    assert "tam sayı kuruş" in rules.SYSTEM_PROMPT
