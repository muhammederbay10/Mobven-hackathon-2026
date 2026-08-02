# ai/normalizer.py
"""Merges raw section outputs into one deterministic rich circular extraction."""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date as Date

from rapidfuzz import fuzz

if __package__:
    from .schema import (
        AppointmentsAgentOutput,
        AuthorityRule,
        ChunkExtractionResult,
        CircularExtraction,
        CompanyRecord,
        DocumentReference,
        ExtractorAgent,
        ExtractorRole,
        ExtractorStatus,
        NotaryRecord,
        PageLabel,
        PageMap,
        RawAppointment,
        RawAuthorityRule,
        RawDocumentReference,
        RawRuleParty,
        RawSpecimen,
        ReferenceResolution,
        RuleConfidence,
        RulePartyRef,
        RulePartyType,
        RuleSigningForm,
        RuleSource,
        RulesAgentOutput,
        SignatoryRecord,
        SourceEvidence,
        SpecimenBoundingBox,
        SpecimensAgentOutput,
    )
    from .turkish import (
        canonicalize_group_code,
        canonicalize_masked_id,
        name_equal,
        tr_normalize,
    )
else:  # scripts may import this module from inside ai/
    from schema import (
        AppointmentsAgentOutput,
        AuthorityRule,
        ChunkExtractionResult,
        CircularExtraction,
        CompanyRecord,
        DocumentReference,
        ExtractorAgent,
        ExtractorRole,
        ExtractorStatus,
        NotaryRecord,
        PageLabel,
        PageMap,
        RawAppointment,
        RawAuthorityRule,
        RawDocumentReference,
        RawRuleParty,
        RawSpecimen,
        ReferenceResolution,
        RuleConfidence,
        RulePartyRef,
        RulePartyType,
        RuleSigningForm,
        RuleSource,
        RulesAgentOutput,
        SignatoryRecord,
        SourceEvidence,
        SpecimenBoundingBox,
        SpecimensAgentOutput,
    )
    from turkish import (
        canonicalize_group_code,
        canonicalize_masked_id,
        name_equal,
        tr_normalize,
    )


DEFAULT_FUZZ_THRESHOLD = 90
UNREADABLE = "UNREADABLE"
_ANNEX_LABELS = frozenset(
    {
        PageLabel.IC_YONERGE_ANNEX,
        PageLabel.BOARD_RESOLUTION_ANNEX,
        PageLabel.GAZETTE_ANNEX,
        PageLabel.IMZA_BEYANNAMESI,
    }
)


class NormalizerConfigurationError(RuntimeError):
    """Raised when deterministic merge configuration is invalid."""


@dataclass
class _PersonDraft:
    name_printed: str
    title: str | None = None
    id_no_masked: str | None = None
    group_code: str | None = None
    valid_from: Date | None = None
    valid_until: Date | None = None
    authority_form: str | None = None
    joint_with_names: list[str] | None = None
    evidence: SourceEvidence | None = None
    specimen_bboxes: list[SpecimenBoundingBox] | None = None


@dataclass(frozen=True)
class _RuleCandidate:
    raw: RawAuthorityRule
    source: RuleSource
    supporting: bool


def normalize_extraction(
    document_id: str,
    page_map: PageMap,
    chunk_results: Sequence[ChunkExtractionResult],
    *,
    fuzzy_threshold: int | None = None,
) -> CircularExtraction:
    """Normalizes valid chunk outputs while retaining every failed or uncertain raw result."""

    threshold = _resolve_fuzzy_threshold(fuzzy_threshold)
    appointments = _appointment_outputs(chunk_results)
    company = _merge_company(appointments, page_map)
    notary = _merge_notary(appointments)
    valid_until = _first_date(output.document_valid_until for output in appointments)
    signatories = _merge_rosters(appointments, _specimen_outputs(chunk_results))
    references = _merge_references(appointments, page_map)
    rules = _merge_rules(chunk_results, page_map, signatories, threshold)

    return CircularExtraction(
        document_id=document_id,
        company=company,
        notary=notary,
        valid_until=valid_until,
        signatories=signatories,
        rules=rules,
        page_map=page_map,
        references=references,
        raw_chunks=[result.model_dump(mode="json") for result in chunk_results],
    )


def _appointment_outputs(
    results: Sequence[ChunkExtractionResult],
) -> list[AppointmentsAgentOutput]:
    return [
        result.output
        for result in results
        if result.status is ExtractorStatus.SUCCESS
        and result.role is ExtractorRole.PRIMARY
        and isinstance(result.output, AppointmentsAgentOutput)
    ]


def _specimen_outputs(
    results: Sequence[ChunkExtractionResult],
) -> list[SpecimensAgentOutput]:
    return [
        result.output
        for result in results
        if result.status is ExtractorStatus.SUCCESS
        and result.role is ExtractorRole.PRIMARY
        and isinstance(result.output, SpecimensAgentOutput)
    ]


def _merge_company(outputs: Sequence[AppointmentsAgentOutput], page_map: PageMap) -> CompanyRecord:
    if not outputs:
        return CompanyRecord(legal_name=page_map.company_name_line or UNREADABLE)
    first = outputs[0].company
    evidence = []
    for output in outputs:
        evidence.extend(output.company.evidence)
    return CompanyRecord(
        legal_name=first.legal_name,
        vkn=first.vkn,
        trade_registry_no=first.trade_registry_no,
        mersis=first.mersis,
        address=first.address,
        evidence=_dedupe_evidence(evidence),
    )


def _merge_notary(outputs: Sequence[AppointmentsAgentOutput]) -> NotaryRecord | None:
    raw = next((output.notary for output in outputs if output.notary is not None), None)
    if raw is None:
        return None
    return NotaryRecord(
        name=raw.name,
        date=_date_or_none(raw.date),
        yevmiye_no=raw.yevmiye_no,
        evidence=_dedupe_evidence(raw.evidence),
    )


def _merge_rosters(
    appointments: Sequence[AppointmentsAgentOutput],
    specimens: Sequence[SpecimensAgentOutput],
) -> list[SignatoryRecord]:
    drafts: list[_PersonDraft] = []
    for output in appointments:
        for appointment in output.appointments:
            existing = _find_person(drafts, appointment.name_printed)
            if existing is None:
                drafts.append(_draft_from_appointment(appointment))
            else:
                _merge_appointment(existing, appointment)

    for output in specimens:
        for specimen in output.specimens:
            existing = _find_person(drafts, specimen.name_printed)
            if existing is None:
                drafts.append(_draft_from_specimen(specimen))
            else:
                _merge_specimen(existing, specimen)

    return [
        SignatoryRecord(
            id=f"sig-{index}",
            name_printed=draft.name_printed,
            name_normalized=tr_normalize(draft.name_printed),
            title=draft.title,
            id_no_masked=canonicalize_masked_id(draft.id_no_masked),
            group_code=draft.group_code,
            valid_from=draft.valid_from,
            valid_until=draft.valid_until,
            authority_form=draft.authority_form,
            joint_with_names=list(draft.joint_with_names or []),
            evidence=draft.evidence,
            specimen_bboxes=list(draft.specimen_bboxes or []),
        )
        for index, draft in enumerate(drafts, start=1)
    ]


def _draft_from_appointment(item: RawAppointment) -> _PersonDraft:
    return _PersonDraft(
        name_printed=item.name_printed,
        title=item.title,
        id_no_masked=item.id_no_masked,
        group_code=item.group_code,
        valid_from=_date_or_none(item.valid_from),
        valid_until=_date_or_none(item.valid_until),
        authority_form=item.authority_form,
        joint_with_names=list(item.joint_with_names),
        evidence=item.evidence,
        specimen_bboxes=[],
    )


def _draft_from_specimen(item: RawSpecimen) -> _PersonDraft:
    return _PersonDraft(
        name_printed=item.name_printed,
        title=item.title,
        group_code=item.group_code,
        joint_with_names=[],
        specimen_bboxes=[item.signature_bbox],
    )


def _merge_appointment(draft: _PersonDraft, item: RawAppointment) -> None:
    draft.title = draft.title or item.title
    draft.id_no_masked = draft.id_no_masked or item.id_no_masked
    draft.group_code = draft.group_code or item.group_code
    draft.valid_from = draft.valid_from or _date_or_none(item.valid_from)
    draft.valid_until = draft.valid_until or _date_or_none(item.valid_until)
    draft.authority_form = draft.authority_form or item.authority_form
    draft.evidence = draft.evidence or item.evidence
    draft.joint_with_names = _unique_names(
        [*(draft.joint_with_names or []), *item.joint_with_names]
    )


def _merge_specimen(draft: _PersonDraft, item: RawSpecimen) -> None:
    draft.title = draft.title or item.title
    draft.group_code = draft.group_code or item.group_code
    bboxes = draft.specimen_bboxes or []
    if item.signature_bbox not in bboxes:
        bboxes.append(item.signature_bbox)
    draft.specimen_bboxes = bboxes


def _find_person(drafts: Sequence[_PersonDraft], printed_name: str) -> _PersonDraft | None:
    if printed_name == UNREADABLE:
        return None
    return next(
        (
            draft
            for draft in drafts
            if draft.name_printed != UNREADABLE and name_equal(draft.name_printed, printed_name)
        ),
        None,
    )


def _merge_references(
    outputs: Sequence[AppointmentsAgentOutput], page_map: PageMap
) -> list[DocumentReference]:
    references: list[DocumentReference] = []
    seen: set[tuple[object, object, object]] = set()
    for raw in (reference for output in outputs for reference in output.references):
        key = (raw.ref_doc_type, _date_or_none(raw.ref_date), raw.ref_number)
        if key in seen:
            continue
        seen.add(key)
        references.append(
            DocumentReference(
                ref_doc_type=raw.ref_doc_type,
                ref_date=_date_or_none(raw.ref_date),
                ref_number=raw.ref_number,
                resolved=_reference_resolution(raw, page_map),
            )
        )
    return references


def _reference_resolution(raw: RawDocumentReference, page_map: PageMap) -> ReferenceResolution:
    matching_label = {
        "ic_yonerge": PageLabel.IC_YONERGE_ANNEX,
        "board_resolution": PageLabel.BOARD_RESOLUTION_ANNEX,
        "gazette": PageLabel.GAZETTE_ANNEX,
    }.get(raw.ref_doc_type.value)
    if matching_label and any(matching_label in page.labels for page in page_map.pages):
        return ReferenceResolution.IN_FILE
    if raw.ref_doc_type.value == "other":
        return ReferenceResolution.UNKNOWN
    return ReferenceResolution.EXTERNAL


def _merge_rules(
    results: Sequence[ChunkExtractionResult],
    page_map: PageMap,
    signatories: Sequence[SignatoryRecord],
    threshold: int,
) -> list[AuthorityRule]:
    primary: list[_RuleCandidate] = []
    supporting: list[_RuleCandidate] = []
    witness: list[_RuleCandidate] = []

    for result in results:
        if result.status is not ExtractorStatus.SUCCESS or not isinstance(
            result.output, RulesAgentOutput
        ):
            continue
        for raw in result.output.rules:
            is_supporting = result.supporting_only or _page_is_annex_only(
                raw.evidence.page, page_map
            )
            candidate = _RuleCandidate(
                raw=raw,
                source=RuleSource.ANNEX if is_supporting else RuleSource.CIRCULAR,
                supporting=is_supporting,
            )
            if result.role is ExtractorRole.WITNESS:
                witness.append(candidate)
            elif is_supporting or result.agent is ExtractorAgent.ANNEX:
                supporting.append(candidate)
            else:
                primary.append(candidate)

    primary = _dedupe_candidates(primary, threshold)
    supporting = _dedupe_candidates(supporting, threshold)
    rules: list[AuthorityRule] = []

    for candidate in primary:
        corroborated = _has_quote_match(candidate, witness, threshold) or _has_quote_match(
            candidate, supporting, threshold
        )
        confidence = RuleConfidence.LOW if candidate.raw.partial else RuleConfidence.MEDIUM
        if corroborated and not candidate.raw.partial:
            confidence = RuleConfidence.HIGH
        rules.append(
            _map_rule(
                candidate.raw,
                candidate.source,
                confidence,
                signatories,
                page_map.structure_hints,
            )
        )

    for candidate in supporting:
        if _has_quote_match(candidate, primary, threshold):
            continue
        rules.append(
            _map_rule(
                candidate.raw,
                RuleSource.ANNEX,
                RuleConfidence.LOW,
                signatories,
                page_map.structure_hints,
            )
        )
    return rules


def _dedupe_candidates(
    candidates: Sequence[_RuleCandidate], threshold: int
) -> list[_RuleCandidate]:
    merged: list[_RuleCandidate] = []
    for candidate in candidates:
        compatible = [
            (index, other)
            for index, other in enumerate(merged)
            if _same_rule_identity(candidate.raw, other.raw)
        ]
        local_match = _best_match_index(
            candidate,
            [other for _, other in compatible],
            threshold,
        )
        match_index = compatible[local_match][0] if local_match is not None else None
        if match_index is None:
            merged.append(candidate)
            continue
        merged[match_index] = _merge_duplicate_candidates(
            merged[match_index], candidate
        )
    return merged


def _same_rule_identity(left: RawAuthorityRule, right: RawAuthorityRule) -> bool:
    """Prevents repeated legal prose from collapsing distinct executable policies."""

    return (
        left.evidence.page == right.evidence.page
        and left.amount_min == right.amount_min
        and left.amount_max == right.amount_max
        and tr_normalize(left.currency or "") == tr_normalize(right.currency or "")
        and left.sole_or_joint == right.sole_or_joint
        and _raw_signing_parties_key(left) == _raw_signing_parties_key(right)
        and _date_or_none(left.valid_until) == _date_or_none(right.valid_until)
    )


def _raw_party_key(party: RawRuleParty) -> tuple[str, str, str]:
    return (
        party.type.value,
        canonicalize_group_code(party.ref)
        if party.type is RulePartyType.GROUP
        else tr_normalize(party.ref or ""),
        tr_normalize(party.name or ""),
    )


def _raw_signing_parties_key(
    rule: RawAuthorityRule,
) -> tuple[tuple[str, str, str], ...]:
    who = _raw_party_key(rule.who)
    joint = tuple(sorted(_raw_party_key(item) for item in rule.joint_with))
    if rule.sole_or_joint is RuleSigningForm.JOINT:
        return tuple(sorted((who, *joint)))
    return (who, *joint)


def _merge_duplicate_candidates(
    left: _RuleCandidate, right: _RuleCandidate
) -> _RuleCandidate:
    preferred, other = (
        (right, left)
        if _candidate_score(right) > _candidate_score(left)
        else (left, right)
    )
    scope_tags = list(preferred.raw.scope_tags)
    seen = {tr_normalize(tag) for tag in scope_tags}
    for tag in other.raw.scope_tags:
        normalized = tr_normalize(tag)
        if normalized not in seen:
            scope_tags.append(tag)
            seen.add(normalized)
    scope_text = max(
        (left.raw.scope_text, right.raw.scope_text),
        key=lambda value: len(tr_normalize(value)),
    )
    return _RuleCandidate(
        raw=preferred.raw.model_copy(
            update={"scope_tags": scope_tags, "scope_text": scope_text}
        ),
        source=preferred.source,
        supporting=preferred.supporting,
    )


def _best_match_index(
    candidate: _RuleCandidate,
    others: Sequence[_RuleCandidate],
    threshold: int,
) -> int | None:
    matches = [
        (index, _quote_similarity(candidate.raw.evidence.quote, other.raw.evidence.quote))
        for index, other in enumerate(others)
    ]
    matches = [item for item in matches if item[1] >= threshold]
    return max(matches, key=lambda item: item[1])[0] if matches else None


def _has_quote_match(
    candidate: _RuleCandidate,
    others: Sequence[_RuleCandidate],
    threshold: int,
) -> bool:
    return _best_match_index(candidate, others, threshold) is not None


def _candidate_score(candidate: _RuleCandidate) -> tuple[int, int]:
    return (int(not candidate.raw.partial), len(candidate.raw.evidence.quote))


def _map_rule(
    raw: RawAuthorityRule,
    source: RuleSource,
    confidence: RuleConfidence,
    signatories: Sequence[SignatoryRecord],
    structure_hints: Sequence[str],
) -> AuthorityRule:
    return AuthorityRule(
        who=_resolve_party(raw.who, signatories, structure_hints),
        sole_or_joint=raw.sole_or_joint,
        joint_with=[
            _resolve_party(party, signatories, structure_hints)
            for party in raw.joint_with
        ],
        amount_min=raw.amount_min,
        amount_max=raw.amount_max,
        currency=raw.currency,
        scope_tags=list(raw.scope_tags),
        scope_text=raw.scope_text,
        valid_until=_date_or_none(raw.valid_until),
        source=source,
        evidence=raw.evidence,
        confidence=confidence,
        partial=raw.partial,
    )


def _resolve_party(
    raw: RawRuleParty,
    signatories: Sequence[SignatoryRecord],
    structure_hints: Sequence[str],
) -> RulePartyRef:
    if raw.type is RulePartyType.GROUP:
        roster_group = _matching_group_code(raw.ref, signatories)
        return RulePartyRef(
            type=RulePartyType.GROUP,
            ref=roster_group or raw.ref,
            note=raw.note,
        )
    assert raw.name is not None
    person = next(
        (item for item in signatories if name_equal(item.name_printed, raw.name)), None
    )
    if person is not None:
        return RulePartyRef(type=RulePartyType.PERSON, ref=person.id, note=raw.note)
    group = _matching_group_code(raw.name, signatories)
    if group is not None:
        return RulePartyRef(type=RulePartyType.GROUP, ref=group, note=raw.note)
    if _group_appears_in_hints(raw.name, structure_hints):
        return RulePartyRef(type=RulePartyType.GROUP, ref=raw.name, note=raw.note)
    return RulePartyRef(
        type=RulePartyType.UNRESOLVED_EXTERNAL,
        name=raw.name,
        note=raw.note or "not defined in this document",
    )


def _group_appears_in_hints(name: str, hints: Sequence[str]) -> bool:
    normalized = tr_normalize(name)
    if not normalized:
        return False
    words = normalized.split()
    for hint in hints:
        hint_normalized = tr_normalize(hint)
        if len(words) == 1 and normalized in hint_normalized.split():
            return True
        if len(words) > 1 and normalized in hint_normalized:
            return True
    return False


def _matching_group_code(
    value: str | None, signatories: Sequence[SignatoryRecord]
) -> str | None:
    target = canonicalize_group_code(value)
    if not target:
        return None
    return next(
        (
            item.group_code
            for item in signatories
            if item.group_code and canonicalize_group_code(item.group_code) == target
        ),
        None,
    )


def _page_is_annex_only(page_number: int, page_map: PageMap) -> bool:
    page = next((item for item in page_map.pages if item.page == page_number), None)
    return bool(
        page
        and PageLabel.RULES not in page.labels
        and any(label in _ANNEX_LABELS for label in page.labels)
    )


def _date_or_none(value: object) -> Date | None:
    return value if isinstance(value, Date) else None


def _first_date(values: Iterable[object]) -> Date | None:
    return next((value for value in values if isinstance(value, Date)), None)


def _dedupe_evidence(values: Iterable[SourceEvidence]) -> list[SourceEvidence]:
    result: list[SourceEvidence] = []
    seen: set[tuple[object, object]] = set()
    for value in values:
        key = (getattr(value, "page", None), getattr(value, "quote", None))
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _unique_names(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if not any(name_equal(value, existing) for existing in result):
            result.append(value)
    return result


def _quote_similarity(left: str, right: str) -> float:
    return fuzz.ratio(tr_normalize(left), tr_normalize(right))


def _resolve_fuzzy_threshold(value: int | None) -> int:
    if value is None:
        raw = os.getenv("FUZZ_THRESHOLD", str(DEFAULT_FUZZ_THRESHOLD))
        try:
            value = int(raw)
        except ValueError as error:
            raise NormalizerConfigurationError("FUZZ_THRESHOLD must be an integer") from error
    if not 0 <= value <= 100:
        raise NormalizerConfigurationError("FUZZ_THRESHOLD must be between 0 and 100")
    return value
