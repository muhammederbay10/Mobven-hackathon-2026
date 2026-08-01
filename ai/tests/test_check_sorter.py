# ai/tests/test_check_sorter.py
"""Offline tests for the sorter diagnostic's record/replay behaviour.

The --live path is exercised by monkeypatching ai.sorter._default_caller with a scripted
stand-in, never a real OpenAI client — this file makes zero external calls despite covering
--live, per the project rule that pytest must never call OpenAI.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pypdfium2 as pdfium
import pytest

from ai.scripts import check_sorter

TWO_PAGE_RESPONSE = json.dumps(
    {
        "pages": [
            {"page": 1, "labels": ["identity_header", "rules"], "continues_on_next": False},
            {"page": 2, "labels": ["specimens", "notary_block"], "continues_on_next": False},
        ]
    }
)


def make_pdf(pages: int) -> bytes:
    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(595, 842)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def fake_default_caller(_model):
    def call(_system_prompt, _user_content):
        return TWO_PAGE_RESPONSE

    return call


def test_live_flag_calls_the_model_and_writes_a_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(check_sorter, "RECORDINGS_DIR", tmp_path / "recordings")
    monkeypatch.setattr("ai.sorter._default_caller", fake_default_caller)
    document = tmp_path / "case1.pdf"
    document.write_bytes(make_pdf(2))

    exit_code = check_sorter.main([str(document), "--live"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "recorded" in output
    digest = check_sorter.digest_of(document)
    assert check_sorter.recording_path(digest).exists()


def test_replay_reads_back_an_existing_recording_without_calling_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(check_sorter, "RECORDINGS_DIR", tmp_path / "recordings")
    document = tmp_path / "case1.pdf"
    document.write_bytes(make_pdf(2))
    digest = check_sorter.digest_of(document)
    record = check_sorter.recording_path(digest)
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(
        json.dumps({"source_sha256": digest, "raw_responses": [TWO_PAGE_RESPONSE]}),
        encoding="utf-8",
    )

    def explode(*_args, **_kwargs):
        raise AssertionError("replay must not call the model")

    monkeypatch.setattr("ai.sorter._default_caller", explode)

    exit_code = check_sorter.main([str(document)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "OK" in output
    assert "specimens" in output


def test_missing_recording_fails_clearly_without_calling_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(check_sorter, "RECORDINGS_DIR", tmp_path / "recordings")
    document = tmp_path / "case1.pdf"
    document.write_bytes(make_pdf(1))

    exit_code = check_sorter.main([str(document)])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "--live" in output


def test_recording_message_survives_a_directory_outside_the_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # tmp_path is not under REPO_ROOT on most systems — relative_to() must not crash the run.
    monkeypatch.setattr(check_sorter, "RECORDINGS_DIR", tmp_path / "recordings")
    monkeypatch.setattr("ai.sorter._default_caller", fake_default_caller)
    document = tmp_path / "case1.pdf"
    document.write_bytes(make_pdf(2))

    exit_code = check_sorter.main([str(document), "--live"])

    assert exit_code == 0
    assert "recorded" in capsys.readouterr().out


def test_a_render_failure_is_reported_and_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    document = tmp_path / "notes.txt"
    document.write_text("plain text", encoding="utf-8")

    exit_code = check_sorter.main([str(document)])

    assert exit_code == 1
    assert "could not render" in capsys.readouterr().out


def test_a_degraded_outcome_is_visible_and_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(check_sorter, "RECORDINGS_DIR", tmp_path / "recordings")
    monkeypatch.setattr("ai.sorter._default_caller", lambda _model: (lambda *_a: "not json"))
    document = tmp_path / "case1.pdf"
    document.write_bytes(make_pdf(1))

    exit_code = check_sorter.main([str(document), "--live"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "DEGRADED" in output
