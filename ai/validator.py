# ai/validator.py
"""Produces deterministic provenance annotations without mutating or gating extraction data."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable, Sequence
from datetime import date as Date

from rapidfuzz import fuzz

if __package__:
    from .schema import (
        ChunkExtractionResult,
        CircularExtraction,
        ExtractorAgent,
        ExtractorRole,
        ExtractorStatus,
        FlagSeverity,
        PageLabel,
        ProvenanceFlag,
        RulePartyType,
        RuleSource,
        RulesAgentOutput,
        ValidationOutcome,
    )
    from .turkish import canonicalize_masked_id, name_equal, parse_tr_date, tr_normalize
else:  # scripts may import this module from inside ai/
    from schema import (
        ChunkExtractionResult,
        CircularExtraction,
        ExtractorAgent,
        ExtractorRole,
        ExtractorStatus,
        FlagSeverity,
        PageLabel,
        ProvenanceFlag,
        RulePartyType,
        RuleSource,
        RulesAgentOutput,
        ValidationOutcome,
    )
    from turkish import canonicalize_masked_id, name_equal, parse_tr_date, tr_normalize


DEFAULT_FUZZ_THRESHOLD = 90
_DATE_PATTERN = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b")
_TCKN = re.compile(r"^\d{11}$")
_VKN = re.compile(r"^\d{10}$")

_SEVERITY_ORDER = {
    FlagSeverity.SERIOUS: 0,
    FlagSeverity.WARN: 1,
    FlagSeverity.INFO: 2,
}
_CHECK_ORDER = {
    "id_checksum": 0,
    "unresolved_reference": 1,
    "validity_missing_or_conflict": 2,
    "model_disagreement": 3,
    "quote_cross_check": 4,
    "structure_sanity": 5,
    "chunk_failed": 6,
    "partial_clause": 7,
    "other_unknown": 8,
    "annex_only_rule": 9,
    "validator_internal_error": 10,
}


def validate_extraction(
    extraction: CircularExtraction,
    *,
    fuzzy_threshold: int | None = None,
) -> ValidationOutcome:
    """Runs every provenance check independently and always returns typed annotations."""

    threshold = _safe_fuzzy_threshold(fuzzy_threshold)
    checks: list[
        tuple[str, Callable[[CircularExtraction, int], list[ProvenanceFlag]]]
    ] = [
        ("id_checksum", _check_id_checksums),
        ("unresolved_reference", _check_unresolved_references),
        ("validity_missing_or_conflict", _check_validity),
        ("model_disagreement", _check_model_disagreement),
        ("quote_cross_check", _check_quotes),
        ("structure_sanity", _check_structure),
        ("pipeline_incidents", _check_pipeline_incidents),
    ]
    flags: list[ProvenanceFlag] = []
    for check_name, check in checks:
        try:
            flags.extend(check(extraction, threshold))
        except Exception as error:  # a broken check is itself an annotation, never a pipeline gate
            flags.append(
                _flag(
                    FlagSeverity.WARN,
                    "validator_internal_error",
                    f"{check_name} doğrulaması çalıştırılamadı: {type(error).__name__}",
                    "provenance_flags",
                    "VALIDATOR_INTERNAL_ERROR",
                )
            )

    flags = _sorted_unique(flags)
    review_fields = _ordered_unique(
        flag.field_path for flag in flags if flag.severity is not FlagSeverity.INFO
    )
    anomaly_codes = _ordered_unique(
        flag.anomaly_code for flag in flags if flag.anomaly_code is not None
    )
    return ValidationOutcome(
        flags=flags,
        fields_needing_review=review_fields,
        anomaly_codes=anomaly_codes,
    )


def is_valid_tckn(value: str) -> bool:
    """Checks the two verification digits of an eleven-digit Turkish identity number."""

    if not _TCKN.fullmatch(value) or value[0] == "0":
        return False
    digits = [int(char) for char in value]
    odd_sum = sum(digits[index] for index in (0, 2, 4, 6, 8))
    even_sum = sum(digits[index] for index in (1, 3, 5, 7))
    return ((odd_sum * 7 - even_sum) % 10 == digits[9]) and (
        sum(digits[:10]) % 10 == digits[10]
    )


def is_valid_vkn(value: str) -> bool:
    """Checks a ten-digit Turkish tax number using its position-weighted check digit."""

    if not _VKN.fullmatch(value):
        return False
    digits = [int(char) for char in value]
    total = 0
    for index, digit in enumerate(digits[:9]):
        position = 9 - index
        shifted = (digit + position) % 10
        contribution = (shifted * (2**position)) % 9
        if shifted != 0 and contribution == 0:
            contribution = 9
        total += contribution
    return (10 - total % 10) % 10 == digits[9]


def _check_id_checksums(
    extraction: CircularExtraction, threshold: int
) -> list[ProvenanceFlag]:
    del threshold
    flags: list[ProvenanceFlag] = []
    vkn = extraction.company.vkn
    if vkn and (not _VKN.fullmatch(vkn) or not is_valid_vkn(vkn)):
        flags.append(
            _flag(
                FlagSeverity.SERIOUS,
                "id_checksum",
                "Vergi kimlik numarası biçim veya sağlama denetiminden geçmedi.",
                "company.vkn",
                "INVALID_VKN",
                _first_company_page(extraction),
            )
        )

    for chunk_index, result in _raw_results(extraction):
        output = result.output
        appointments = getattr(output, "appointments", []) if output is not None else []
        for appointment_index, appointment in enumerate(appointments):
            value = appointment.id_no_masked
            if not value:
                continue
            field_path = (
                f"raw_chunks[{chunk_index}].output."
                f"appointments[{appointment_index}].id_no_masked"
            )
            canonical = canonicalize_masked_id(value)
            if canonical:
                if value.strip() != canonical:
                    flags.append(
                        _flag(
                            FlagSeverity.WARN,
                            "id_checksum",
                            "Maskeli T.C. kimlik numarası standart gösterime dönüştürüldü.",
                            field_path,
                            "MASK_NORMALIZED",
                            appointment.evidence.page,
                        )
                    )
                continue
            if not _TCKN.fullmatch(value) or not is_valid_tckn(value):
                flags.append(
                    _flag(
                        FlagSeverity.SERIOUS,
                        "id_checksum",
                        "T.C. kimlik numarası biçim veya sağlama denetiminden geçmedi.",
                        field_path,
                        "INVALID_TCKN",
                        appointment.evidence.page,
                    )
                )
    return flags


def _check_unresolved_references(
    extraction: CircularExtraction, threshold: int
) -> list[ProvenanceFlag]:
    del threshold
    flags: list[ProvenanceFlag] = []
    for rule_index, rule in enumerate(extraction.rules):
        parties = [("who", rule.who), *(
            (f"joint_with[{index}]", party)
            for index, party in enumerate(rule.joint_with)
        )]
        for suffix, party in parties:
            if party.type is RulePartyType.UNRESOLVED_EXTERNAL:
                flags.append(
                    _flag(
                        FlagSeverity.WARN,
                        "unresolved_reference",
                        f"Belgede tanımlanamayan imza tarafı: {party.name}.",
                        f"rules[{rule_index}].{suffix}",
                        "UNRESOLVED_REFERENCE",
                        rule.evidence.page,
                    )
                )

    known_groups = {
        tr_normalize(item.group_code)
        for item in extraction.signatories
        if item.group_code
    }
    for signatory_index, signatory in enumerate(extraction.signatories):
        for joint_index, printed_name in enumerate(signatory.joint_with_names):
            resolved_person = any(
                name_equal(printed_name, candidate.name_printed)
                for candidate in extraction.signatories
            )
            if resolved_person or tr_normalize(printed_name) in known_groups:
                continue
            flags.append(
                _flag(
                    FlagSeverity.WARN,
                    "unresolved_reference",
                    f"Müşterek imza tarafı kişi listesinde bulunamadı: {printed_name}.",
                    f"signatories[{signatory_index}].joint_with_names[{joint_index}]",
                    "UNRESOLVED_REFERENCE",
                    signatory.evidence.page if signatory.evidence else None,
                )
            )
    return flags


def _check_validity(
    extraction: CircularExtraction, threshold: int
) -> list[ProvenanceFlag]:
    del threshold
    flags: list[ProvenanceFlag] = []
    for index, signatory in enumerate(extraction.signatories):
        quote = signatory.evidence.quote if signatory.evidence else ""
        page = signatory.evidence.page if signatory.evidence else None
        dates = _dates_in_quote(quote)
        field = f"signatories[{index}].valid_until"
        if signatory.valid_until is None:
            if dates:
                flags.append(
                    _flag(
                        FlagSeverity.SERIOUS,
                        "validity_missing_or_conflict",
                        "Kanıt alıntısında tarih var ancak temsilci geçerlilik tarihi boş.",
                        field,
                        "VALIDITY_DATE_DROPPED",
                        page,
                    )
                )
            elif not _explicitly_indefinite(quote):
                flags.append(
                    _flag(
                        FlagSeverity.WARN,
                        "validity_missing_or_conflict",
                        "Temsilci için geçerlilik bitiş tarihi belgelenemedi.",
                        field,
                        "VALIDITY_MISSING",
                        page,
                    )
                )
        elif dates and "tarihine kadar" in tr_normalize(quote):
            if signatory.valid_until not in dates:
                flags.append(
                    _flag(
                        FlagSeverity.SERIOUS,
                        "validity_missing_or_conflict",
                        "Temsilci geçerlilik tarihi kanıt alıntısındaki tarihle çelişiyor.",
                        field,
                        "VALIDITY_CONFLICT",
                        page,
                    )
                )
    return flags


def _check_model_disagreement(
    extraction: CircularExtraction, threshold: int
) -> list[ProvenanceFlag]:
    flags: list[ProvenanceFlag] = []
    for chunk_index, primary, witness in _rule_result_pairs(extraction):
        for primary_index, primary_rule in enumerate(primary.rules):
            witness_rule = _best_raw_rule_match(primary_rule, witness.rules, threshold)
            if witness_rule is None:
                continue
            fields = {
                "sole_or_joint": (primary_rule.sole_or_joint, witness_rule.sole_or_joint),
                "amount_min": (primary_rule.amount_min, witness_rule.amount_min),
                "amount_max": (primary_rule.amount_max, witness_rule.amount_max),
                "joint_with": (
                    _raw_parties_key(primary_rule.joint_with),
                    _raw_parties_key(witness_rule.joint_with),
                ),
            }
            for field_name, (left, right) in fields.items():
                if left == right:
                    continue
                flags.append(
                    _flag(
                        FlagSeverity.WARN,
                        "model_disagreement",
                        "Birincil okuyucu ile tanık okuyucu "
                        f"{field_name} alanında farklı sonuç verdi.",
                        f"raw_chunks[{chunk_index}].output.rules[{primary_index}].{field_name}",
                        "MODEL_DISAGREEMENT",
                        primary_rule.evidence.page,
                    )
                )
    return flags


def _check_quotes(
    extraction: CircularExtraction, threshold: int
) -> list[ProvenanceFlag]:
    flags: list[ProvenanceFlag] = []
    for chunk_index, primary, witness in _rule_result_pairs(extraction):
        for index, rule in enumerate(primary.rules):
            if _best_raw_rule_match(rule, witness.rules, threshold) is not None:
                continue
            flags.append(
                _flag(
                    FlagSeverity.WARN,
                    "quote_cross_check",
                    "Birincil kural alıntısı tanık okumasında eşleşmedi.",
                    f"raw_chunks[{chunk_index}].output.rules[{index}].evidence.quote",
                    "QUOTE_NOT_CORROBORATED",
                    rule.evidence.page,
                )
            )
    return flags


def _check_structure(
    extraction: CircularExtraction, threshold: int
) -> list[ProvenanceFlag]:
    flags: list[ProvenanceFlag] = []
    labels = {label for page in extraction.page_map.pages for label in page.labels}
    if PageLabel.APPOINTMENTS not in labels:
        flags.append(
            _flag(
                FlagSeverity.SERIOUS,
                "structure_sanity",
                "Belgede temsilci atamaları bölümü sınıflandırılmadı.",
                "page_map.pages",
                "APPOINTMENTS_SECTION_MISSING",
            )
        )
    if PageLabel.NOTARY_BLOCK not in labels:
        flags.append(
            _flag(
                FlagSeverity.WARN,
                "structure_sanity",
                "Belgede noter bloğu sınıflandırılmadı.",
                "page_map.pages",
                "NOTARY_BLOCK_MISSING",
            )
        )
    if not extraction.signatories:
        flags.append(
            _flag(
                FlagSeverity.SERIOUS,
                "structure_sanity",
                "Temsilci listesi boş çıkarıldı.",
                "signatories",
                "SIGNATORY_ROSTER_EMPTY",
            )
        )

    limited = [
        (index, item)
        for index, item in enumerate(extraction.signatories)
        if item.authority_form
        and any(
            token in tr_normalize(item.authority_form)
            for token in ("sinirli yetkili", "ic yonergede")
        )
    ]
    authoritative_rules = [
        rule
        for rule in extraction.rules
        if rule.source in {RuleSource.CIRCULAR, RuleSource.DIRECTIVE}
    ]
    if limited and not authoritative_rules:
        flags.append(
            _flag(
                FlagSeverity.SERIOUS,
                "structure_sanity",
                "Sınırlı yetki ataması var ancak birincil yetki kuralları "
                "çıkarılamadı; iç yönergeyi isteyin.",
                "rules",
                "AUTHORITY_RULES_INCOMPLETE",
                limited[0][1].evidence.page if limited[0][1].evidence else None,
            )
        )

    for index, signatory in enumerate(extraction.signatories):
        if signatory.evidence is not None and not signatory.specimen_bboxes:
            flags.append(
                _flag(
                    FlagSeverity.INFO,
                    "structure_sanity",
                    "Atama kaydı var ancak tatbik imzası bulunamadı.",
                    f"signatories[{index}].specimen_bboxes",
                    "APPOINTMENT_WITHOUT_SPECIMEN",
                    signatory.evidence.page,
                )
            )
        elif signatory.evidence is None and signatory.specimen_bboxes:
            flags.append(
                _flag(
                    FlagSeverity.WARN,
                    "structure_sanity",
                    "Tatbik imzası var ancak atama kaydı bulunamadı.",
                    f"signatories[{index}].evidence",
                    "SPECIMEN_WITHOUT_APPOINTMENT",
                    signatory.specimen_bboxes[0].page,
                )
            )

    appointed = [item for item in extraction.signatories if item.evidence is not None]
    specimen_only = [item for item in extraction.signatories if item.evidence is None]
    for left in appointed:
        for right in specimen_only:
            similarity = fuzz.ratio(
                tr_normalize(left.name_printed), tr_normalize(right.name_printed)
            )
            if similarity >= threshold and not name_equal(left.name_printed, right.name_printed):
                flags.append(
                    _flag(
                        FlagSeverity.INFO,
                        "structure_sanity",
                        f"Olası yazım farkı: {left.name_printed} / {right.name_printed}.",
                        "signatories",
                        "POSSIBLE_ROSTER_MATCH",
                    )
                )
    return flags


def _check_pipeline_incidents(
    extraction: CircularExtraction, threshold: int
) -> list[ProvenanceFlag]:
    del threshold
    flags: list[ProvenanceFlag] = []
    parsed_indexes = {index for index, _ in _raw_results(extraction)}
    for index, raw in enumerate(extraction.raw_chunks):
        if index not in parsed_indexes:
            flags.append(
                _flag(
                    FlagSeverity.SERIOUS,
                    "chunk_failed",
                    "Ham parça kaydı doğrulanamadı.",
                    f"raw_chunks[{index}]",
                    "RAW_CHUNK_INVALID",
                )
            )
    for index, result in _raw_results(extraction):
        if result.status is ExtractorStatus.FAILED:
            flags.append(
                _flag(
                    FlagSeverity.SERIOUS,
                    "chunk_failed",
                    f"{result.chunk_id} iki denemeden sonra çıkarılamadı.",
                    f"raw_chunks[{index}]",
                    "CHUNK_FAILED",
                )
            )

    for index, rule in enumerate(extraction.rules):
        if rule.partial:
            flags.append(
                _flag(
                    FlagSeverity.WARN,
                    "partial_clause",
                    "Yetki hükmü sayfa sınırında eksik kalmış olabilir.",
                    f"rules[{index}]",
                    "PARTIAL_CLAUSE",
                    rule.evidence.page,
                )
            )
        if rule.source is RuleSource.ANNEX:
            flags.append(
                _flag(
                    FlagSeverity.WARN,
                    "annex_only_rule",
                    "Bu hüküm yalnızca destekleyici ekte bulundu; yeni yetki olarak kullanılamaz.",
                    f"rules[{index}]",
                    "ANNEX_ONLY_RULE",
                    rule.evidence.page,
                )
            )

    for page in extraction.page_map.pages:
        if PageLabel.OTHER_UNKNOWN in page.labels:
            flags.append(
                _flag(
                    FlagSeverity.SERIOUS,
                    "other_unknown",
                    "Sayfa sınıflandırılamadı ve insan incelemesi gerekiyor.",
                    f"page_map.pages[{page.page - 1}]",
                    "OTHER_UNKNOWN_PAGE",
                    page.page,
                )
            )
    return flags


def _raw_results(
    extraction: CircularExtraction,
) -> list[tuple[int, ChunkExtractionResult]]:
    parsed = []
    for index, raw in enumerate(extraction.raw_chunks):
        try:
            parsed.append((index, ChunkExtractionResult.model_validate(raw)))
        except Exception:
            continue
    return parsed


def _rule_result_pairs(
    extraction: CircularExtraction,
) -> list[tuple[int, RulesAgentOutput, RulesAgentOutput]]:
    primary: dict[str, tuple[int, RulesAgentOutput]] = {}
    witness: dict[str, RulesAgentOutput] = {}
    for raw_index, result in _raw_results(extraction):
        if (
            result.status is not ExtractorStatus.SUCCESS
            or result.agent is not ExtractorAgent.RULES
            or not isinstance(result.output, RulesAgentOutput)
        ):
            continue
        if result.role is ExtractorRole.WITNESS:
            witness[result.chunk_id] = result.output
        else:
            primary[result.chunk_id] = (raw_index, result.output)
    return [
        (raw_index, output, witness[chunk_id])
        for chunk_id, (raw_index, output) in primary.items()
        if chunk_id in witness
    ]


def _best_raw_rule_match(rule, candidates: Sequence, threshold: int):
    matches = [
        (candidate, _quote_similarity(rule.evidence.quote, candidate.evidence.quote))
        for candidate in candidates
    ]
    matches = [item for item in matches if item[1] >= threshold]
    return max(matches, key=lambda item: item[1])[0] if matches else None


def _raw_parties_key(parties: Sequence) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        sorted(
            (
                party.type.value,
                tr_normalize(party.ref or ""),
                tr_normalize(party.name or ""),
            )
            for party in parties
        )
    )


def _dates_in_quote(quote: str) -> list[Date]:
    dates: list[Date] = []
    for raw in _DATE_PATTERN.findall(quote):
        try:
            dates.append(parse_tr_date(raw))
        except ValueError:
            continue
    return dates


def _explicitly_indefinite(quote: str) -> bool:
    normalized = tr_normalize(quote)
    return any(
        phrase in normalized
        for phrase in ("aksi karar alinincaya kadar", "suresiz", "belirsiz sureli")
    )


def _first_company_page(extraction: CircularExtraction) -> int | None:
    return extraction.company.evidence[0].page if extraction.company.evidence else None


def _flag(
    severity: FlagSeverity,
    check_name: str,
    message: str,
    field_path: str,
    anomaly_code: str,
    evidence_page: int | None = None,
) -> ProvenanceFlag:
    return ProvenanceFlag(
        severity=severity,
        check_name=check_name,
        message=message,
        field_path=field_path,
        evidence_page=evidence_page,
        anomaly_code=anomaly_code,
    )


def _sorted_unique(flags: Sequence[ProvenanceFlag]) -> list[ProvenanceFlag]:
    unique: dict[tuple[object, ...], ProvenanceFlag] = {}
    for flag in flags:
        key = (
            flag.severity,
            flag.check_name,
            flag.field_path,
            flag.anomaly_code,
            flag.evidence_page,
        )
        unique.setdefault(key, flag)
    return sorted(
        unique.values(),
        key=lambda flag: (
            _SEVERITY_ORDER[flag.severity],
            _CHECK_ORDER.get(flag.check_name, 99),
            flag.field_path,
            flag.anomaly_code or "",
        ),
    )


def _ordered_unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _quote_similarity(left: str, right: str) -> float:
    return fuzz.ratio(tr_normalize(left), tr_normalize(right))


def _safe_fuzzy_threshold(value: int | None) -> int:
    raw = os.getenv("FUZZ_THRESHOLD", str(DEFAULT_FUZZ_THRESHOLD)) if value is None else str(value)
    try:
        parsed = int(raw)
    except ValueError:
        return DEFAULT_FUZZ_THRESHOLD
    return parsed if 0 <= parsed <= 100 else DEFAULT_FUZZ_THRESHOLD
