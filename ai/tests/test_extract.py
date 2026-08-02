# ai/tests/test_extract.py
"""Offline end-to-end, cache, projection, and degradation tests for the orchestrator."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from ai.chunker import Chunk, build_chunks
from ai.extract import PipelineDependencies, extract_document, project_extraction
from ai.main import app
from ai.normalizer import normalize_extraction
from ai.render import PageImages
from ai.schema import (
    AppointmentsAgentOutput,
    AuthorityRule,
    ChunkExtractionResult,
    CircularExtraction,
    CompanyRecord,
    ExtractorAgent,
    ExtractorRole,
    ExtractorStatus,
    FlagSeverity,
    PageClassification,
    PageLabel,
    PageMap,
    PipelineMode,
    RawAppointment,
    RawAuthorityRule,
    RawCompanyExtraction,
    RawNotaryExtraction,
    RawRuleParty,
    RawSpecimen,
    RuleConfidence,
    RulePartyRef,
    RulePartyType,
    RuleSigningForm,
    RuleSource,
    RulesAgentOutput,
    SourceEvidence,
    SpecimenBoundingBox,
    SpecimensAgentOutput,
    ValidationOutcome,
)
from ai.sorter import SorterOutcome
from ai.validator import validate_extraction


def _page_map() -> PageMap:
    return PageMap(
        company_name_line="ACME ANONİM ŞİRKETİ",
        pages=[
            PageClassification(
                page=1,
                labels=[
                    PageLabel.IDENTITY_HEADER,
                    PageLabel.APPOINTMENTS,
                    PageLabel.RULES,
                    PageLabel.SPECIMENS,
                    PageLabel.NOTARY_BLOCK,
                ],
            )
        ],
    )


def _rendered_pages() -> list[PageImages]:
    return [
        PageImages(
            page_no=1,
            sort_png=b"sort-image",
            extract_png=b"extract-image",
            sort_size=(100, 100),
            extract_size=(250, 250),
        )
    ]


def _success_result(
    chunk_id: str,
    agent: ExtractorAgent,
    output,
) -> ChunkExtractionResult:
    return ChunkExtractionResult(
        chunk_id=chunk_id,
        agent=agent,
        role=ExtractorRole.PRIMARY,
        status=ExtractorStatus.SUCCESS,
        model="offline-test",
        attempts=1,
        output=output,
    )


def _chunk_results() -> list[ChunkExtractionResult]:
    appointment_quote = "ALİ YILMAZ 31.12.2030 tarihine kadar münferiden yetkilidir."
    rule_quote = "ALİ YILMAZ 500.000,00 TL'ye kadar münferiden imzaya yetkilidir."
    appointments = AppointmentsAgentOutput(
        company=RawCompanyExtraction(
            legal_name="ACME ANONİM ŞİRKETİ",
            vkn="8500712792",
            evidence=[SourceEvidence(page=1, quote="ACME ANONİM ŞİRKETİ")],
        ),
        notary=RawNotaryExtraction(
            name="İstanbul 1. Noterliği",
            date="2026-01-01",
            yevmiye_no="1234",
        ),
        document_valid_until="2030-12-31",
        appointments=[
            RawAppointment(
                name_printed="ALİ YILMAZ",
                id_no_masked="123******01",
                authority_form="münferiden",
                valid_until="2030-12-31",
                evidence=SourceEvidence(page=1, quote=appointment_quote),
            )
        ],
    )
    rules = RulesAgentOutput(
        rules=[
            RawAuthorityRule(
                who=RawRuleParty(type=RulePartyType.PERSON, name="Ali Yılmaz"),
                sole_or_joint=RuleSigningForm.SOLE,
                amount_max=50_000_000,
                currency="TRY",
                scope_tags=["general"],
                scope_text="Genel işlemler",
                evidence=SourceEvidence(page=1, quote=rule_quote),
            )
        ]
    )
    specimens = SpecimensAgentOutput(
        specimens=[
            RawSpecimen(
                name_printed="Ali Yılmaz",
                signature_bbox=SpecimenBoundingBox(
                    page=1, x0=0.1, y0=0.1, x1=0.3, y1=0.2
                ),
            )
        ]
    )
    return [
        _success_result("appointments_p1", ExtractorAgent.APPOINTMENTS, appointments),
        _success_result("rules_p1", ExtractorAgent.RULES, rules),
        _success_result("specimens_p1", ExtractorAgent.SPECIMENS, specimens),
    ]


async def _fake_extract(chunks: Sequence[Chunk]) -> list[ChunkExtractionResult]:
    assert chunks
    return _chunk_results()


def _dependencies(**overrides) -> PipelineDependencies:
    values = {
        "render": lambda data, filename: _rendered_pages(),
        "sort": lambda pages: SorterOutcome(
            page_map=_page_map(),
            degraded=False,
            attempts=1,
            raw_responses=("sorter raw response",),
        ),
        "chunk": build_chunks,
        "extract": _fake_extract,
        "normalize": normalize_extraction,
        "validate": validate_extraction,
        "project": project_extraction,
    }
    values.update(overrides)
    return PipelineDependencies(**values)


@pytest.mark.asyncio
async def test_live_pipeline_runs_every_stage_and_projects_flat_contract(tmp_path: Path) -> None:
    outcome = await extract_document(
        b"synthetic-document",
        "test.pdf",
        "doc-live",
        mode="live",
        cache_enabled=False,
        cache_dir=tmp_path,
        dependencies=_dependencies(),
    )

    assert outcome.degraded is False
    assert outcome.cache_hit is False
    assert outcome.page_count == 1
    assert outcome.chunk_count == 3
    assert [timing.stage for timing in outcome.timings] == [
        "render",
        "sort",
        "chunk",
        "extract",
        "normalize",
        "validate",
        "project",
    ]
    assert outcome.sorter_raw_responses == ("sorter raw response",)
    assert outcome.result.document_id == "doc-live"
    assert outcome.result.representatives[0].id == "rep-1"
    assert outcome.result.representatives[0].mode.value == "SOLE"
    assert outcome.result.representatives[0].limits == 50_000_000
    assert outcome.result.rules[0].threshold == 50_000_000
    assert outcome.result.evidence.authority_clause.startswith("ALİ YILMAZ")


@pytest.mark.asyncio
async def test_cache_hit_and_replay_never_call_live_stages(tmp_path: Path) -> None:
    data = b"cache-me"
    first = await extract_document(
        data,
        "test.pdf",
        "doc-first",
        mode=PipelineMode.LIVE,
        cache_enabled=True,
        cache_dir=tmp_path,
        dependencies=_dependencies(),
    )
    cache_file = tmp_path / f"{first.source_sha256}.json"
    assert cache_file.exists()
    cached_text = cache_file.read_text(encoding="utf-8")
    assert "sorter raw response" in cached_text
    assert "raw_chunks" in cached_text

    def forbidden_render(data, filename):
        raise AssertionError("cache hit must not render")

    second = await extract_document(
        data,
        "renamed.pdf",
        "doc-second",
        mode="live",
        cache_enabled=True,
        cache_dir=tmp_path,
        dependencies=_dependencies(render=forbidden_render),
    )
    replay = await extract_document(
        data,
        "renamed.pdf",
        "doc-replay",
        mode="replay",
        cache_enabled=False,
        cache_dir=tmp_path,
        dependencies=_dependencies(render=forbidden_render),
    )

    assert second.cache_hit is True
    assert second.result.document_id == "doc-second"
    assert replay.cache_hit is True
    assert replay.mode is PipelineMode.REPLAY
    assert replay.result.document_id == "doc-replay"
    assert replay.result.model_dump(exclude={"document_id"}) == second.result.model_dump(
        exclude={"document_id"}
    )


@pytest.mark.asyncio
async def test_cache_off_ignores_an_existing_live_entry(tmp_path: Path) -> None:
    data = b"cache-off"
    await extract_document(
        data,
        "test.pdf",
        "doc-cached",
        mode="live",
        cache_enabled=True,
        cache_dir=tmp_path,
        dependencies=_dependencies(),
    )
    called = False

    def fresh_render(data, filename):
        nonlocal called
        called = True
        return _rendered_pages()

    outcome = await extract_document(
        data,
        "test.pdf",
        "doc-fresh",
        mode="live",
        cache_enabled=False,
        cache_dir=tmp_path,
        dependencies=_dependencies(render=fresh_render),
    )

    assert called is True
    assert outcome.cache_hit is False


@pytest.mark.asyncio
async def test_replay_miss_degrades_without_running_live_stages(tmp_path: Path) -> None:
    def forbidden_render(data, filename):
        raise AssertionError("replay must never call live stages")

    outcome = await extract_document(
        b"not-cached",
        "test.pdf",
        "doc-miss",
        mode="replay",
        cache_dir=tmp_path,
        dependencies=_dependencies(render=forbidden_render),
    )

    assert outcome.degraded is True
    assert outcome.cache_hit is False
    assert outcome.result.fields_needing_review == ["pipeline.replay"]
    assert outcome.result.model_dump(mode="json", by_alias=True)["schema_version"] == "1.0"


def _raise(error: Exception):
    def raising(*args, **kwargs):
        raise error

    return raising


async def _raise_async(*args, **kwargs):
    raise RuntimeError("injected async failure")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("override", "expected_field"),
    [
        ({"render": _raise(RuntimeError("render failed"))}, "pipeline.render"),
        ({"sort": _raise(RuntimeError("sort failed"))}, "pipeline.sorter"),
        ({"chunk": _raise(RuntimeError("chunk failed"))}, "pipeline.chunker"),
        ({"extract": _raise_async}, "pipeline.extractors"),
        ({"normalize": _raise(RuntimeError("normalize failed"))}, "pipeline.normalizer"),
        ({"validate": _raise(RuntimeError("validate failed"))}, "pipeline.validator"),
        ({"project": _raise(RuntimeError("project failed"))}, "pipeline.projection"),
    ],
)
async def test_each_stage_failure_returns_a_reviewable_schema(
    tmp_path: Path,
    override: dict,
    expected_field: str,
) -> None:
    outcome = await extract_document(
        b"failure-case",
        "test.pdf",
        "doc-failure",
        mode="live",
        cache_enabled=False,
        cache_dir=tmp_path,
        dependencies=_dependencies(**override),
    )

    payload = outcome.result.model_dump(mode="json", by_alias=True)
    assert outcome.degraded is True
    assert expected_field in payload["fieldsNeedingReview"]
    assert payload["schema_version"] == "1.0"
    assert payload["document_id"] == "doc-failure"


@pytest.mark.asyncio
async def test_stub_and_http_endpoint_use_the_frozen_external_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    direct = await extract_document(
        b"ignored-in-stub",
        "case2.pdf",
        "doc_02",
        mode="stub",
    )
    assert direct.degraded is False
    assert direct.result.representatives[0].mode.value == "JOINT"

    monkeypatch.setenv("AI_MODE", "stub")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/extract",
            data={"document_id": "doc_03"},
            files={"file": ("belge-ç.pdf", b"stub bytes", "application/pdf")},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "1.0"
    assert payload["document_id"] == "doc_03"
    assert payload["company"]["name"] == "Zeta İnşaat Sanayi ve Ticaret Anonim Şirketi"


def test_projection_expands_joint_groups_omits_annex_and_blocks_exclusions() -> None:
    evidence = SourceEvidence(page=1, quote="A ve B grupları müştereken imzalar.")
    signatories = normalize_extraction(
        "projection",
        _page_map(),
        _chunk_results(),
    ).signatories
    signatories[0].group_code = "A"
    second = signatories[0].model_copy(
        update={
            "id": "sig-2",
            "name_printed": "AYŞE DEMİR",
            "name_normalized": "ayse demir",
            "group_code": "B",
        }
    )
    joint = AuthorityRule(
        who=RulePartyRef(type=RulePartyType.GROUP, ref="A"),
        sole_or_joint=RuleSigningForm.JOINT,
        joint_with=[RulePartyRef(type=RulePartyType.GROUP, ref="B")],
        scope_tags=["general"],
        scope_text="Genel işlemler",
        source=RuleSource.CIRCULAR,
        evidence=evidence,
        confidence=RuleConfidence.HIGH,
    )
    blocked = AuthorityRule(
        who=RulePartyRef(type=RulePartyType.GROUP, ref="A"),
        sole_or_joint=RuleSigningForm.SOLE,
        scope_tags=["real_estate"],
        scope_text="Gayrimenkul işlemleri kapsam dışıdır.",
        source=RuleSource.CIRCULAR,
        evidence=SourceEvidence(page=1, quote="Gayrimenkul işlemleri kapsam dışıdır."),
        confidence=RuleConfidence.HIGH,
    )
    annex = joint.model_copy(update={"source": RuleSource.ANNEX})
    circular = CircularExtraction(
        document_id="projection",
        company=CompanyRecord(legal_name="ACME ANONİM ŞİRKETİ"),
        signatories=[signatories[0], second],
        rules=[joint, blocked, annex],
        page_map=_page_map(),
    )

    result = project_extraction(circular, ValidationOutcome())

    assert len(result.rules) == 2
    assert result.rules[0].co_signers == ["rep-1", "rep-2"]
    assert result.rules[1].blocked is True
    assert result.rules[1].mode is None
    assert result.representatives[0].co_signers == ["AYŞE DEMİR"]


def test_projection_keeps_an_unresolved_joint_clause_as_blocked_evidence() -> None:
    signatory = normalize_extraction("projection", _page_map(), _chunk_results()).signatories[0]
    signatory.group_code = "A"
    unresolved = AuthorityRule(
        who=RulePartyRef(type=RulePartyType.GROUP, ref="A Grubu"),
        sole_or_joint=RuleSigningForm.JOINT,
        joint_with=[
            RulePartyRef(
                type=RulePartyType.UNRESOLVED_EXTERNAL,
                name="BELGEDE TANIMLANMAYAN KİŞİ",
            )
        ],
        scope_tags=["general"],
        scope_text="Genel işlemler",
        source=RuleSource.CIRCULAR,
        evidence=SourceEvidence(page=1, quote="A grubu ve dış kişi müştereken imzalar."),
        confidence=RuleConfidence.LOW,
    )
    circular = CircularExtraction(
        document_id="projection",
        company=CompanyRecord(legal_name="ACME ANONİM ŞİRKETİ"),
        signatories=[signatory],
        rules=[unresolved],
        page_map=_page_map(),
    )

    result = project_extraction(circular, ValidationOutcome())

    assert len(result.rules) == 1
    assert result.rules[0].blocked is True
    assert result.rules[0].mode is None
    assert result.rules[0].co_signers == []
    assert result.rules[0].evidence == unresolved.evidence
    assert "rules[0].joint_with" in result.fields_needing_review


def test_projection_resolves_roman_and_written_degree_aliases() -> None:
    first = normalize_extraction("projection", _page_map(), _chunk_results()).signatories[0]
    first.group_code = "1. derece"
    second = first.model_copy(
        update={
            "id": "sig-2",
            "name_printed": "AYŞE DEMİR",
            "name_normalized": "ayse demir",
            "group_code": "İkinci Derece",
        }
    )
    joint = AuthorityRule(
        who=RulePartyRef(type=RulePartyType.GROUP, ref="I. Derece"),
        sole_or_joint=RuleSigningForm.JOINT,
        joint_with=[
            RulePartyRef(type=RulePartyType.GROUP, ref="II. Derece İmza Yetkilileri")
        ],
        scope_tags=["general"],
        scope_text="Genel işlemler",
        source=RuleSource.CIRCULAR,
        evidence=SourceEvidence(page=1, quote="I. ve II. derece müştereken imzalar."),
        confidence=RuleConfidence.HIGH,
    )
    circular = CircularExtraction(
        document_id="projection",
        company=CompanyRecord(legal_name="ACME ANONİM ŞİRKETİ"),
        signatories=[first, second],
        rules=[joint],
        page_map=_page_map(),
    )

    result = project_extraction(circular, ValidationOutcome())

    assert result.rules[0].blocked is False
    assert result.rules[0].co_signers == ["rep-1", "rep-2"]
    assert "rules[0].joint_with" not in result.fields_needing_review


@pytest.mark.asyncio
async def test_invalid_mode_is_a_degraded_contract_not_an_exception() -> None:
    outcome = await extract_document(
        b"data",
        "test.pdf",
        "doc-mode",
        mode="unknown",
    )

    assert outcome.degraded is True
    assert outcome.result.fields_needing_review == ["pipeline.mode"]
