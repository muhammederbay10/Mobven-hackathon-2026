# ai/tests/test_normalizer.py
"""Offline regressions for deterministic chunk merging and reference resolution."""

from __future__ import annotations

from ai.normalizer import NormalizerConfigurationError, normalize_extraction
from ai.schema import (
    AppointmentsAgentOutput,
    ChunkExtractionResult,
    ExtractorAgent,
    ExtractorRole,
    ExtractorStatus,
    PageClassification,
    PageLabel,
    PageMap,
    RawAppointment,
    RawAuthorityRule,
    RawCompanyExtraction,
    RawDocumentReference,
    RawRuleParty,
    RawSpecimen,
    ReferenceResolution,
    RuleConfidence,
    RulePartyType,
    RuleSigningForm,
    RuleSource,
    RulesAgentOutput,
    SourceEvidence,
    SpecimenBoundingBox,
    SpecimensAgentOutput,
)


def evidence(page: int, quote: str) -> SourceEvidence:
    return SourceEvidence(page=page, quote=quote)


def result(
    chunk_id: str,
    agent: ExtractorAgent,
    output,
    *,
    role: ExtractorRole = ExtractorRole.PRIMARY,
    supporting: bool = False,
) -> ChunkExtractionResult:
    return ChunkExtractionResult(
        chunk_id=chunk_id,
        agent=agent,
        role=role,
        status=ExtractorStatus.SUCCESS,
        model="offline-test",
        supporting_only=supporting,
        attempts=1,
        output=output,
    )


def page_map() -> PageMap:
    return PageMap(
        company_name_line="ACME ANONİM ŞİRKETİ",
        structure_hints=["A ve B grupları vardır"],
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
            ),
            PageClassification(page=2, labels=[PageLabel.RULES]),
            PageClassification(page=3, labels=[PageLabel.RULES]),
            PageClassification(
                page=4, labels=[PageLabel.RULES, PageLabel.IC_YONERGE_ANNEX]
            ),
        ],
    )


def appointment_output() -> AppointmentsAgentOutput:
    return AppointmentsAgentOutput(
        company=RawCompanyExtraction(
            legal_name="ACME ANONİM ŞİRKETİ",
            vkn="8500712792",
            evidence=[evidence(1, "ACME ANONİM ŞİRKETİ")],
        ),
        document_valid_until="2030-12-31",
        appointments=[
            RawAppointment(
                name_printed="ALİ YILMAZ",
                group_code="A",
                joint_with_names=["TOLGA AKAR"],
                valid_until="2023-12-12",
                evidence=evidence(1, "ALİ YILMAZ 12.12.2023 tarihine kadar yetkilidir."),
            ),
            RawAppointment(
                name_printed="GÜSEVA",
                group_code="B",
                evidence=evidence(1, "GÜSEVA B grubu yetkilisidir."),
            ),
        ],
        references=[
            RawDocumentReference(
                ref_doc_type="ic_yonerge",
                ref_number="7",
                evidence=evidence(1, "7 sayılı iç yönerge"),
            )
        ],
    )


def specimen_output() -> SpecimensAgentOutput:
    return SpecimensAgentOutput(
        specimens=[
            RawSpecimen(
                name_printed="Ali Yılmaz",
                group_code="A",
                signature_bbox=SpecimenBoundingBox(
                    page=1, x0=0.1, y0=0.1, x1=0.3, y1=0.2
                ),
            ),
            RawSpecimen(
                name_printed="CUSKYA",
                group_code="B",
                signature_bbox=SpecimenBoundingBox(
                    page=1, x0=0.4, y0=0.1, x1=0.6, y1=0.2
                ),
            ),
        ]
    )


def raw_rule(
    quote: str,
    *,
    page: int = 2,
    partial: bool = False,
    who: RawRuleParty | None = None,
    joint_with: list[RawRuleParty] | None = None,
) -> RawAuthorityRule:
    return RawAuthorityRule(
        who=who or RawRuleParty(type=RulePartyType.GROUP, ref="A"),
        sole_or_joint=RuleSigningForm.JOINT,
        joint_with=joint_with or [RawRuleParty(type=RulePartyType.GROUP, ref="B")],
        amount_min=50000001,
        currency="TRY",
        scope_tags=["general"],
        scope_text="500.000,00 TL üzerindeki işlemler",
        evidence=evidence(page, quote),
        partial=partial,
    )


def test_normalizer_dedupes_joins_resolves_and_applies_annex_precedence() -> None:
    shared_quote = "500.000,00 TL üzerindeki işlemlerde A ve B müştereken imzalar."
    unresolved_quote = "ALİ YILMAZ ve TOLGA AKAR müştereken imzalar."
    annex_quote = "Yalnız ekte bulunan destekleyici hüküm."
    partial = raw_rule(shared_quote, partial=True)
    complete = raw_rule(shared_quote)
    unresolved = raw_rule(
        unresolved_quote,
        page=3,
        who=RawRuleParty(type=RulePartyType.PERSON, name="Ali Yılmaz"),
        joint_with=[RawRuleParty(type=RulePartyType.PERSON, name="TOLGA AKAR")],
    )
    chunks = [
        result("appointments_p1", ExtractorAgent.APPOINTMENTS, appointment_output()),
        result("specimens_p1", ExtractorAgent.SPECIMENS, specimen_output()),
        result("rules_p2-3", ExtractorAgent.RULES, RulesAgentOutput(rules=[partial, unresolved])),
        result("rules_p3", ExtractorAgent.RULES, RulesAgentOutput(rules=[complete])),
        result(
            "rules_p2-3",
            ExtractorAgent.RULES,
            RulesAgentOutput(rules=[complete]),
            role=ExtractorRole.WITNESS,
        ),
        result(
            "annex_p4",
            ExtractorAgent.ANNEX,
            RulesAgentOutput(rules=[complete, raw_rule(annex_quote, page=4)]),
            supporting=True,
        ),
    ]

    normalized = normalize_extraction("doc-1", page_map(), chunks, fuzzy_threshold=90)

    assert normalized.document_id == "doc-1"
    assert normalized.valid_until.isoformat() == "2030-12-31"
    assert len(normalized.signatories) == 3
    assert normalized.signatories[0].name_printed == "ALİ YILMAZ"
    assert normalized.signatories[0].specimen_bboxes
    assert normalized.signatories[0].valid_until.isoformat() == "2023-12-12"
    assert normalized.signatories[1].name_printed == "GÜSEVA"
    assert not normalized.signatories[1].specimen_bboxes
    assert normalized.signatories[2].name_printed == "CUSKYA"
    assert normalized.signatories[2].evidence is None
    assert normalized.signatories[0].joint_with_names == ["TOLGA AKAR"]

    assert len(normalized.rules) == 3
    merged = normalized.rules[0]
    assert merged.partial is False
    assert merged.confidence is RuleConfidence.HIGH
    assert merged.source is RuleSource.CIRCULAR
    unresolved_rule = normalized.rules[1]
    assert unresolved_rule.who.ref == normalized.signatories[0].id
    assert unresolved_rule.joint_with[0].type is RulePartyType.UNRESOLVED_EXTERNAL
    assert unresolved_rule.joint_with[0].name == "TOLGA AKAR"
    annex_rule = normalized.rules[2]
    assert annex_rule.source is RuleSource.ANNEX
    assert annex_rule.confidence is RuleConfidence.LOW

    assert normalized.references[0].resolved is ReferenceResolution.IN_FILE
    assert len(normalized.raw_chunks) == len(chunks)


def test_rules_on_mixed_rule_and_annex_pages_remain_primary_authority() -> None:
    chunks = [
        result("appointments_p1", ExtractorAgent.APPOINTMENTS, appointment_output()),
        result(
            "rules_p4",
            ExtractorAgent.RULES,
            RulesAgentOutput(rules=[raw_rule("Ek hükmü", page=4)]),
        ),
    ]

    normalized = normalize_extraction("doc-annex", page_map(), chunks)

    assert len(normalized.rules) == 1
    assert normalized.rules[0].source is RuleSource.CIRCULAR


def test_rules_on_annex_only_pages_remain_supporting_material() -> None:
    annex_map = page_map().model_copy(
        update={
            "pages": [
                PageClassification(page=4, labels=[PageLabel.IC_YONERGE_ANNEX])
            ]
        }
    )
    chunks = [
        result(
            "rules_p4",
            ExtractorAgent.RULES,
            RulesAgentOutput(rules=[raw_rule("Ek hükmü", page=4)]),
        ),
    ]

    normalized = normalize_extraction("doc-annex-only", annex_map, chunks)

    assert normalized.rules[0].source is RuleSource.ANNEX


def test_nonstandard_source_mask_is_canonicalized_without_losing_raw_value() -> None:
    appointments = appointment_output().model_copy(deep=True)
    appointments.appointments[0].id_no_masked = "681********38"
    chunks = [result("appointments_p1", ExtractorAgent.APPOINTMENTS, appointments)]

    normalized = normalize_extraction("doc-mask", page_map(), chunks)

    assert normalized.signatories[0].id_no_masked == "681******38"
    assert (
        normalized.raw_chunks[0]["output"]["appointments"][0]["id_no_masked"]
        == "681********38"
    )


def test_unmatched_partial_survives_with_low_confidence() -> None:
    chunks = [
        result("appointments_p1", ExtractorAgent.APPOINTMENTS, appointment_output()),
        result(
            "rules_p2",
            ExtractorAgent.RULES,
            RulesAgentOutput(rules=[raw_rule("Kesilmiş hüküm...", partial=True)]),
        ),
    ]

    normalized = normalize_extraction("doc-partial", page_map(), chunks)

    assert normalized.rules[0].partial is True
    assert normalized.rules[0].confidence is RuleConfidence.LOW


def test_name_like_party_resolves_to_group_when_structure_hint_defines_it() -> None:
    hint_map = page_map().model_copy(
        update={"structure_hints": ["A ve B grupları vardır"]}
    )
    name_like_group = raw_rule(
        "A grubu müştereken imzalar.",
        who=RawRuleParty(type=RulePartyType.PERSON, name="A"),
    )
    chunks = [
        result(
            "rules_p2",
            ExtractorAgent.RULES,
            RulesAgentOutput(rules=[name_like_group]),
        )
    ]

    normalized = normalize_extraction("doc-hint", hint_map, chunks)

    assert normalized.rules[0].who.type is RulePartyType.GROUP
    assert normalized.rules[0].who.ref == "A"


def test_failed_appointments_degrade_to_page_map_company_without_dropping_raw_chunk() -> None:
    failed = ChunkExtractionResult(
        chunk_id="appointments_p1",
        agent=ExtractorAgent.APPOINTMENTS,
        role=ExtractorRole.PRIMARY,
        status=ExtractorStatus.FAILED,
        model="offline-test",
        attempts=2,
        chunk_failed=True,
        error="invalid JSON",
    )

    normalized = normalize_extraction("doc-failed", page_map(), [failed])

    assert normalized.company.legal_name == "ACME ANONİM ŞİRKETİ"
    assert normalized.signatories == []
    assert normalized.raw_chunks[0]["chunk_failed"] is True


def test_fuzzy_threshold_configuration_is_validated(monkeypatch) -> None:
    monkeypatch.setenv("FUZZ_THRESHOLD", "not-an-integer")
    try:
        normalize_extraction("doc", page_map(), [])
    except NormalizerConfigurationError as error:
        assert "FUZZ_THRESHOLD" in str(error)
    else:
        raise AssertionError("invalid FUZZ_THRESHOLD should fail explicitly")
