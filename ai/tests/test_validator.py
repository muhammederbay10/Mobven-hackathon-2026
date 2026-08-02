# ai/tests/test_validator.py
"""Offline provenance regressions prove flags annotate but never mutate extraction data."""

from __future__ import annotations

from copy import deepcopy

from ai.schema import (
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
    RawAuthorityRule,
    RawRuleParty,
    RuleConfidence,
    RulePartyRef,
    RulePartyType,
    RuleSigningForm,
    RuleSource,
    RulesAgentOutput,
    SignatoryRecord,
    SourceEvidence,
    SpecimenBoundingBox,
)
from ai.validator import is_valid_tckn, is_valid_vkn, validate_extraction


def evidence(quote: str, page: int = 1) -> SourceEvidence:
    return SourceEvidence(page=page, quote=quote)


def page_map(*, unknown: bool = False, complete: bool = True) -> PageMap:
    labels = [PageLabel.RULES]
    if complete:
        labels.extend([PageLabel.APPOINTMENTS, PageLabel.NOTARY_BLOCK])
    if unknown:
        labels.append(PageLabel.OTHER_UNKNOWN)
    return PageMap(pages=[PageClassification(page=1, labels=labels)])


def signatory(
    *,
    valid_until="2027-12-12",
    quote: str = "ALİ YILMAZ 12.12.2027 tarihine kadar yetkilidir.",
    authority_form: str | None = None,
    with_specimen: bool = True,
) -> SignatoryRecord:
    return SignatoryRecord(
        id="sig-1",
        name_printed="ALİ YILMAZ",
        name_normalized="ali yilmaz",
        group_code="A",
        valid_until=valid_until,
        authority_form=authority_form,
        evidence=evidence(quote),
        specimen_bboxes=(
            [SpecimenBoundingBox(page=1, x0=0.1, y0=0.1, x1=0.2, y1=0.2)]
            if with_specimen
            else []
        ),
    )


def rule(
    quote: str = "A grubu münferiden imzalar.",
    *,
    source: RuleSource = RuleSource.CIRCULAR,
    partial: bool = False,
    who: RulePartyRef | None = None,
) -> AuthorityRule:
    return AuthorityRule(
        who=who or RulePartyRef(type=RulePartyType.GROUP, ref="A"),
        sole_or_joint=RuleSigningForm.SOLE,
        amount_max=50000000,
        currency="TRY",
        scope_tags=["general"],
        scope_text="genel",
        source=source,
        evidence=evidence(quote),
        confidence=RuleConfidence.HIGH,
        partial=partial,
    )


def extraction(**changes) -> CircularExtraction:
    values = {
        "document_id": "doc-1",
        "company": CompanyRecord(
            legal_name="ACME ANONİM ŞİRKETİ",
            vkn="8500712792",
            evidence=[evidence("VKN 8500712792")],
        ),
        "signatories": [signatory()],
        "rules": [rule()],
        "page_map": page_map(),
        "raw_chunks": [],
    }
    values.update(changes)
    return CircularExtraction(**values)


def raw_rule(
    quote: str,
    *,
    amount_max: int = 50000000,
    joint: bool = False,
) -> RawAuthorityRule:
    return RawAuthorityRule(
        who=RawRuleParty(type=RulePartyType.GROUP, ref="A"),
        sole_or_joint=RuleSigningForm.JOINT if joint else RuleSigningForm.SOLE,
        joint_with=(
            [RawRuleParty(type=RulePartyType.GROUP, ref="B")] if joint else []
        ),
        amount_max=amount_max,
        currency="TRY",
        scope_tags=["general"],
        scope_text="genel",
        evidence=evidence(quote),
    )


def raw_result(
    role: ExtractorRole,
    rules: list[RawAuthorityRule],
) -> dict:
    return ChunkExtractionResult(
        chunk_id="rules_p1",
        agent=ExtractorAgent.RULES,
        role=role,
        status=ExtractorStatus.SUCCESS,
        model="offline-test",
        attempts=1,
        output=RulesAgentOutput(rules=rules),
    ).model_dump(mode="json")


def codes(result) -> set[str]:
    return set(result.anomaly_codes)


def test_valid_checksums_and_clean_structure_do_not_raise_required_flags() -> None:
    assert is_valid_tckn("10000000146") is True
    assert is_valid_tckn("10000000145") is False
    assert is_valid_vkn("8500712792") is True
    assert is_valid_vkn("8500712793") is False

    outcome = validate_extraction(extraction())

    assert "INVALID_VKN" not in codes(outcome)
    assert "VALIDITY_MISSING" not in codes(outcome)
    assert "APPOINTMENTS_SECTION_MISSING" not in codes(outcome)


def test_bad_vkn_and_unmasked_tckn_are_serious_checksum_flags() -> None:
    appointment_raw = {
        "chunk_id": "appointments_p1",
        "agent": "appointments",
        "role": "primary",
        "status": "success",
        "model": "offline-test",
        "attempts": 1,
        "output": {
            "company": {"legal_name": "ACME", "evidence": []},
            "appointments": [
                {
                    "name_printed": "ALİ YILMAZ",
                    "id_no_masked": "10000000145",
                    "evidence": {"page": 1, "quote": "10000000145"},
                }
            ],
            "references": [],
        },
    }
    damaged = extraction(
        company=CompanyRecord(legal_name="ACME", vkn="8500712793"),
        raw_chunks=[appointment_raw],
    )

    outcome = validate_extraction(damaged)

    assert {"INVALID_VKN", "INVALID_TCKN"} <= codes(outcome)
    checksum_flags = [flag for flag in outcome.flags if flag.check_name == "id_checksum"]
    assert all(flag.severity is FlagSeverity.SERIOUS for flag in checksum_flags)


def test_nonstandard_mask_is_a_review_warning_instead_of_invalid_tckn() -> None:
    appointment_raw = {
        "chunk_id": "appointments_p1",
        "agent": "appointments",
        "role": "primary",
        "status": "success",
        "model": "offline-test",
        "attempts": 1,
        "output": {
            "company": {"legal_name": "ACME", "evidence": []},
            "appointments": [
                {
                    "name_printed": "ALİ YILMAZ",
                    "id_no_masked": "681********38",
                    "evidence": {"page": 1, "quote": "681********38"},
                }
            ],
            "references": [],
        },
    }

    outcome = validate_extraction(extraction(raw_chunks=[appointment_raw]))

    assert "MASK_NORMALIZED" in codes(outcome)
    assert "INVALID_TCKN" not in codes(outcome)
    flag = next(item for item in outcome.flags if item.anomaly_code == "MASK_NORMALIZED")
    assert flag.severity is FlagSeverity.WARN


def test_unreadable_and_non_tckn_identifiers_are_reviewed_without_false_checksum_flags() -> None:
    appointment_raw = {
        "chunk_id": "appointments_p1",
        "agent": "appointments",
        "role": "primary",
        "status": "success",
        "model": "offline-test",
        "attempts": 1,
        "output": {
            "company": {"legal_name": "ACME", "evidence": []},
            "appointments": [
                {
                    "name_printed": "ALİ YILMAZ",
                    "id_no_masked": "UNREADABLE",
                    "evidence": {"page": 1, "quote": "Kimlik alanı boş"},
                },
                {
                    "name_printed": "JANE DOE",
                    "id_no_masked": "AT6418688",
                    "evidence": {"page": 1, "quote": "Passport No: AT6418688"},
                },
            ],
            "references": [],
        },
    }

    outcome = validate_extraction(extraction(raw_chunks=[appointment_raw]))

    assert "IDENTITY_UNREADABLE" in codes(outcome)
    assert "IDENTITY_TYPE_UNKNOWN" in codes(outcome)
    assert "INVALID_TCKN" not in codes(outcome)
    identity_flags = [
        flag
        for flag in outcome.flags
        if flag.anomaly_code in {"IDENTITY_UNREADABLE", "IDENTITY_TYPE_UNKNOWN"}
    ]
    assert all(flag.severity is FlagSeverity.WARN for flag in identity_flags)


def test_tolga_and_dropped_12122023_date_remain_visible() -> None:
    unresolved = rule(
        who=RulePartyRef(
            type=RulePartyType.UNRESOLVED_EXTERNAL,
            name="TOLGA AKAR",
        )
    )
    person = signatory(valid_until=None, quote="12.12.2023 tarihine kadar yetkilidir.")
    person.joint_with_names.append("TOLGA AKAR")
    damaged = extraction(signatories=[person], rules=[unresolved])

    outcome = validate_extraction(damaged)

    assert "UNRESOLVED_REFERENCE" in codes(outcome)
    assert "VALIDITY_DATE_DROPPED" in codes(outcome)
    date_flag = next(flag for flag in outcome.flags if flag.anomaly_code == "VALIDITY_DATE_DROPPED")
    assert date_flag.severity is FlagSeverity.SERIOUS


def test_explicit_indefinite_authority_does_not_create_missing_validity_flag() -> None:
    person = signatory(
        valid_until=None,
        quote="ALİ YILMAZ aksi karar alınıncaya kadar yetkilidir.",
    )

    outcome = validate_extraction(extraction(signatories=[person]))

    assert "VALIDITY_MISSING" not in codes(outcome)
    assert "VALIDITY_DATE_DROPPED" not in codes(outcome)


def test_witness_disagreement_and_unmatched_quote_are_field_level_flags() -> None:
    shared = "A grubu 500.000 TL'ye kadar münferiden imzalar."
    invented = "Bu alıntı tanıkta bulunmuyor."
    primary = raw_result(
        ExtractorRole.PRIMARY,
        [raw_rule(shared), raw_rule(invented)],
    )
    witness = raw_result(
        ExtractorRole.WITNESS,
        [raw_rule(shared, amount_max=40000000, joint=True)],
    )

    outcome = validate_extraction(extraction(raw_chunks=[primary, witness]))

    disagreement_paths = {
        flag.field_path
        for flag in outcome.flags
        if flag.anomaly_code == "MODEL_DISAGREEMENT"
    }
    assert any(path.endswith("amount_max") for path in disagreement_paths)
    assert any(path.endswith("sole_or_joint") for path in disagreement_paths)
    assert any(path.endswith("joint_with") for path in disagreement_paths)
    assert "QUOTE_NOT_CORROBORATED" in codes(outcome)


def test_empty_primary_rule_chunk_is_a_serious_completeness_failure() -> None:
    empty_primary = raw_result(ExtractorRole.PRIMARY, [])

    outcome = validate_extraction(
        extraction(rules=[], raw_chunks=[empty_primary])
    )

    assert "RULES_SECTION_EMPTY" in codes(outcome)
    assert "RULE_CHUNK_EMPTY" in codes(outcome)
    completeness = [
        flag
        for flag in outcome.flags
        if flag.anomaly_code in {"RULES_SECTION_EMPTY", "RULE_CHUNK_EMPTY"}
    ]
    assert all(flag.severity is FlagSeverity.SERIOUS for flag in completeness)


def test_structure_and_pipeline_incidents_are_all_annotations() -> None:
    failed = ChunkExtractionResult(
        chunk_id="rules_p2",
        agent=ExtractorAgent.RULES,
        role=ExtractorRole.PRIMARY,
        status=ExtractorStatus.FAILED,
        model="offline-test",
        attempts=2,
        chunk_failed=True,
        error="invalid JSON",
    ).model_dump(mode="json")
    damaged = extraction(
        signatories=[
            signatory(
                authority_form="Sınırlı Yetkili (İç yönergede belirtilen şekilde)",
                with_specimen=False,
            )
        ],
        rules=[
            rule(source=RuleSource.ANNEX, partial=True),
        ],
        page_map=page_map(unknown=True, complete=False),
        raw_chunks=[failed, {"malformed": True}],
    )
    before = deepcopy(damaged.model_dump(mode="json"))

    outcome = validate_extraction(damaged)

    assert {
        "APPOINTMENTS_SECTION_MISSING",
        "NOTARY_BLOCK_MISSING",
        "AUTHORITY_RULES_INCOMPLETE",
        "CHUNK_FAILED",
        "RAW_CHUNK_INVALID",
        "PARTIAL_CLAUSE",
        "OTHER_UNKNOWN_PAGE",
        "ANNEX_ONLY_RULE",
    } <= codes(outcome)
    assert damaged.model_dump(mode="json") == before
    severities = [flag.severity for flag in outcome.flags]
    ranks = {FlagSeverity.SERIOUS: 0, FlagSeverity.WARN: 1, FlagSeverity.INFO: 2}
    assert [ranks[item] for item in severities] == sorted(ranks[item] for item in severities)
    assert outcome.fields_needing_review


def test_bad_threshold_falls_back_without_raising(monkeypatch) -> None:
    monkeypatch.setenv("FUZZ_THRESHOLD", "broken")
    outcome = validate_extraction(extraction())
    assert outcome.flags == []
