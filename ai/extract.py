# ai/extract.py
"""Runs the resilient linear extraction pipeline and projects its reviewable flat response."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from pydantic import ValidationError

if __package__:
    from .chunker import Chunk, build_chunks
    from .extractors import extract_chunks
    from .normalizer import normalize_extraction
    from .render import PageImages, render_document
    from .schema import (
        AuthorityClauseEvidence,
        AuthorityRule,
        ChunkExtractionResult,
        CircularExtraction,
        CompanyRecord,
        ExtractionCacheEntry,
        ExtractionCompany,
        ExtractionNotary,
        ExtractionResult,
        ExtractionRule,
        ExtractorStatus,
        FlagSeverity,
        PageClassification,
        PageLabel,
        PageMap,
        PipelineMode,
        PipelineStageStatus,
        PipelineStageTiming,
        ProvenanceFlag,
        Representative,
        RulePartyRef,
        RulePartyType,
        RuleSigningForm,
        RuleSource,
        SignatureMode,
        SourceEvidence,
        ValidationOutcome,
    )
    from .sorter import SorterOutcome, classify_pages
    from .turkish import tr_normalize
    from .validator import validate_extraction
else:  # scripts may import this module from inside ai/
    from chunker import Chunk, build_chunks
    from extractors import extract_chunks
    from normalizer import normalize_extraction
    from render import PageImages, render_document
    from schema import (
        AuthorityClauseEvidence,
        AuthorityRule,
        ChunkExtractionResult,
        CircularExtraction,
        CompanyRecord,
        ExtractionCacheEntry,
        ExtractionCompany,
        ExtractionNotary,
        ExtractionResult,
        ExtractionRule,
        ExtractorStatus,
        FlagSeverity,
        PageClassification,
        PageLabel,
        PageMap,
        PipelineMode,
        PipelineStageStatus,
        PipelineStageTiming,
        ProvenanceFlag,
        Representative,
        RulePartyRef,
        RulePartyType,
        RuleSigningForm,
        RuleSource,
        SignatureMode,
        SourceEvidence,
        ValidationOutcome,
    )
    from sorter import SorterOutcome, classify_pages
    from turkish import tr_normalize
    from validator import validate_extraction


Renderer = Callable[[bytes, str | None], list[PageImages]]
Sorter = Callable[[Sequence[PageImages]], SorterOutcome]
Chunker = Callable[[PageMap, Sequence[PageImages]], list[Chunk]]
Extractor = Callable[[Sequence[Chunk]], Awaitable[list[ChunkExtractionResult]]]
Normalizer = Callable[[str, PageMap, Sequence[ChunkExtractionResult]], CircularExtraction]
Validator = Callable[[CircularExtraction], ValidationOutcome]
Projector = Callable[[CircularExtraction, ValidationOutcome, Sequence[str]], ExtractionResult]

CACHE_DIRECTORY = Path(__file__).with_name("cache") / "extractions"
STUB_DIRECTORY = Path(__file__).with_name("tests") / "fixtures"
_CACHE_ON = frozenset({"1", "true", "yes", "on"})
_NON_SCOPE_TAGS = frozenset({"unlimited"})
_BLOCKED_PHRASES = (
    "kapsam disi",
    "yetkili degildir",
    "yetki disinda",
    "ayrica karar aranir",
)


@dataclass(frozen=True)
class PipelineDependencies:
    """Injection points used by offline failure tests; production uses the real stages."""

    render: Renderer = render_document
    sort: Sorter = classify_pages
    chunk: Chunker = build_chunks
    extract: Extractor = extract_chunks
    normalize: Normalizer = normalize_extraction
    validate: Validator = validate_extraction
    project: Projector | None = None


@dataclass(frozen=True)
class PipelineOutcome:
    result: ExtractionResult
    circular: CircularExtraction | None
    source_sha256: str
    mode: PipelineMode
    timings: tuple[PipelineStageTiming, ...]
    sorter_raw_responses: tuple[str, ...]
    page_count: int
    chunk_count: int
    cache_hit: bool
    degraded: bool


async def extract_document(
    data: bytes,
    filename: str | None,
    document_id: str,
    *,
    mode: PipelineMode | str | None = None,
    cache_enabled: bool | None = None,
    cache_dir: Path | None = None,
    stub_dir: Path | None = None,
    dependencies: PipelineDependencies | None = None,
) -> PipelineOutcome:
    """Runs live extraction or serves a schema-equivalent stub/replay without leaking failures."""

    source_sha256 = hashlib.sha256(data).hexdigest()
    try:
        resolved_mode = _resolve_mode(mode)
    except ValueError as error:
        return _direct_degraded_outcome(
            document_id, source_sha256, PipelineMode.LIVE, "mode", error
        )

    if resolved_mode is PipelineMode.STUB:
        return _stub_outcome(
            document_id,
            source_sha256,
            stub_dir or STUB_DIRECTORY,
        )

    target_cache = cache_dir or CACHE_DIRECTORY
    enabled = _cache_enabled(cache_enabled)
    entry: ExtractionCacheEntry | None = None
    cache_error: Exception | None = None
    if resolved_mode is PipelineMode.REPLAY or enabled:
        entry, cache_error = _read_cache(target_cache, source_sha256)
        if entry is not None:
            return _outcome_from_cache(entry, document_id, resolved_mode)
    if resolved_mode is PipelineMode.REPLAY:
        error = cache_error or FileNotFoundError("sha256 replay artifact not found")
        return _direct_degraded_outcome(
            document_id, source_sha256, resolved_mode, "replay", error
        )

    deps = dependencies or PipelineDependencies()
    project = deps.project or project_extraction
    timings: list[PipelineStageTiming] = []
    incidents: list[ProvenanceFlag] = []
    sorter_raw: tuple[str, ...] = ()
    pages: list[PageImages] = []
    chunks: list[Chunk] = []
    chunk_results: list[ChunkExtractionResult] = []

    started = perf_counter()
    try:
        pages = deps.render(data, filename)
        _timing(timings, "render", started)
    except Exception as error:
        _timing(timings, "render", started, error)
        outcome = _direct_degraded_outcome(
            document_id,
            source_sha256,
            resolved_mode,
            "render",
            error,
            timings=timings,
        )
        return _write_outcome_cache(outcome, target_cache) if enabled else outcome

    started = perf_counter()
    try:
        sorter_outcome = deps.sort(pages)
        page_map = sorter_outcome.page_map
        sorter_raw = sorter_outcome.raw_responses
        if sorter_outcome.degraded:
            error = RuntimeError("sorter exhausted both attempts")
            incidents.append(_pipeline_flag("sorter", error))
            _timing(timings, "sort", started, error)
        else:
            _timing(timings, "sort", started)
    except Exception as error:
        page_map = _unknown_page_map(len(pages), error)
        incidents.append(_pipeline_flag("sorter", error))
        _timing(timings, "sort", started, error)

    started = perf_counter()
    try:
        chunks = deps.chunk(page_map, pages)
        _timing(timings, "chunk", started)
    except Exception as error:
        incidents.append(_pipeline_flag("chunker", error))
        _timing(timings, "chunk", started, error)

    started = perf_counter()
    try:
        chunk_results = await deps.extract(chunks)
        failed = sum(result.status is ExtractorStatus.FAILED for result in chunk_results)
        detail = f"{failed} chunk reading(s) failed" if failed else None
        _timing(
            timings,
            "extract",
            started,
            RuntimeError(detail) if detail else None,
        )
    except Exception as error:
        incidents.append(_pipeline_flag("extractors", error))
        _timing(timings, "extract", started, error)

    started = perf_counter()
    try:
        circular = deps.normalize(document_id, page_map, chunk_results)
        _timing(timings, "normalize", started)
    except Exception as error:
        incidents.append(_pipeline_flag("normalizer", error))
        circular = _empty_circular(document_id, page_map, chunk_results)
        _timing(timings, "normalize", started, error)

    if incidents:
        circular = circular.model_copy(
            update={"provenance_flags": [*circular.provenance_flags, *incidents]}
        )

    started = perf_counter()
    try:
        validation = deps.validate(circular)
        _timing(timings, "validate", started)
    except Exception as error:
        flag = _pipeline_flag("validator", error)
        incidents.append(flag)
        validation = ValidationOutcome(
            flags=[flag],
            fields_needing_review=[flag.field_path],
            anomaly_codes=[flag.anomaly_code] if flag.anomaly_code else [],
        )
        _timing(timings, "validate", started, error)

    combined_flags = _unique_flags([*circular.provenance_flags, *validation.flags])
    circular = circular.model_copy(update={"provenance_flags": combined_flags})
    review_fields = _ordered_unique(
        [
            *validation.fields_needing_review,
            *(flag.field_path for flag in incidents),
        ]
    )

    started = perf_counter()
    try:
        result = project(circular, validation, review_fields)
        _timing(timings, "project", started)
    except Exception as error:
        review_fields.append("pipeline.projection")
        result = _degraded_result(document_id, review_fields, circular)
        incidents.append(_pipeline_flag("projection", error))
        _timing(timings, "project", started, error)

    degraded = bool(incidents) or any(
        result.status is ExtractorStatus.FAILED for result in chunk_results
    )
    outcome = PipelineOutcome(
        result=result,
        circular=circular,
        source_sha256=source_sha256,
        mode=resolved_mode,
        timings=tuple(timings),
        sorter_raw_responses=sorter_raw,
        page_count=len(pages),
        chunk_count=len(chunks),
        cache_hit=False,
        degraded=degraded,
    )
    return _write_outcome_cache(outcome, target_cache) if enabled else outcome


def project_extraction(
    extraction: CircularExtraction,
    validation: ValidationOutcome,
    additional_review: Sequence[str] = (),
) -> ExtractionResult:
    """Projects the rich extraction into the frozen API shape without model judgment."""

    id_map = {
        signatory.id: f"rep-{index}"
        for index, signatory in enumerate(extraction.signatories, start=1)
    }
    review_fields = _ordered_unique(
        [*validation.fields_needing_review, *additional_review]
    )
    representatives: list[Representative] = []
    for index, signatory in enumerate(extraction.signatories):
        mode, limit, co_signers, uncertain = _representative_authority(
            signatory.id,
            signatory.group_code,
            signatory.authority_form,
            signatory.joint_with_names,
            extraction,
            id_map,
        )
        if uncertain:
            review_fields.append(f"representatives[{index}].mode")
        representatives.append(
            Representative(
                id=id_map[signatory.id],
                name=signatory.name_printed,
                national_id=signatory.id_no_masked,
                title=signatory.title,
                mode=mode,
                co_signers=co_signers,
                limits=limit,
            )
        )

    flat_rules: list[ExtractionRule] = []
    for index, rule in enumerate(extraction.rules):
        if rule.source is RuleSource.ANNEX:
            continue
        mapped = _project_rule(rule, extraction, id_map)
        if mapped is None:
            review_fields.append(f"rules[{index}].joint_with")
            continue
        flat_rules.extend(mapped)

    evidence = _authority_evidence(extraction)
    return ExtractionResult(
        document_id=extraction.document_id,
        company=ExtractionCompany(
            name=extraction.company.legal_name or "UNREADABLE",
            tax_number=extraction.company.vkn,
            mersis_number=extraction.company.mersis,
        ),
        notary=ExtractionNotary(
            name=extraction.notary.name if extraction.notary else None,
            date=extraction.notary.date if extraction.notary else None,
            yevmiye=extraction.notary.yevmiye_no if extraction.notary else None,
        ),
        valid_until=extraction.valid_until,
        representatives=representatives,
        fields_needing_review=_ordered_unique(review_fields),
        evidence=evidence,
        rules=flat_rules,
    )


def _representative_authority(
    signatory_id: str,
    group_code: str | None,
    authority_form: str | None,
    printed_joint_names: Sequence[str],
    extraction: CircularExtraction,
    id_map: dict[str, str],
) -> tuple[SignatureMode, int | None, list[str], bool]:
    signatory_rep_id = id_map[signatory_id]
    usable_rules = [rule for rule in extraction.rules if not _is_blocked(rule)]
    sole_rules = [
        rule
        for rule in usable_rules
        if rule.sole_or_joint is RuleSigningForm.SOLE
        and _party_contains(rule.who, signatory_id, group_code)
    ]
    joint_rules = [
        rule
        for rule in usable_rules
        if rule.sole_or_joint is RuleSigningForm.JOINT
        and signatory_rep_id in (_joint_rule_ids(rule, extraction, id_map) or [])
    ]

    if sole_rules:
        general = [rule for rule in sole_rules if "general" in rule.scope_tags]
        relevant = general or sole_rules
        limit = None if any(rule.amount_max is None for rule in relevant) else max(
            rule.amount_max for rule in relevant if rule.amount_max is not None
        )
        return SignatureMode.SOLE, limit, [], False

    if joint_rules:
        names = list(printed_joint_names)
        by_rep_id = {
            id_map[item.id]: item.name_printed for item in extraction.signatories
        }
        for rule in joint_rules:
            for rep_id in _joint_rule_ids(rule, extraction, id_map) or []:
                if rep_id != signatory_rep_id:
                    names.append(by_rep_id[rep_id])
        return SignatureMode.JOINT, None, _ordered_unique(names), False

    normalized_form = tr_normalize(authority_form or "")
    if "munferit" in normalized_form:
        return SignatureMode.SOLE, None, [], False
    if "musterek" in normalized_form:
        return SignatureMode.JOINT, None, list(printed_joint_names), False
    return SignatureMode.JOINT, None, list(printed_joint_names), True


def _project_rule(
    rule: AuthorityRule,
    extraction: CircularExtraction,
    id_map: dict[str, str],
) -> list[ExtractionRule] | None:
    blocked = _is_blocked(rule)
    mode = None if blocked else SignatureMode(rule.sole_or_joint.value.upper())
    co_signers: list[str] = []
    if mode is SignatureMode.JOINT:
        resolved = _joint_rule_ids(rule, extraction, id_map)
        if not resolved:
            return None
        co_signers = resolved

    scopes = [tag for tag in rule.scope_tags if tag not in _NON_SCOPE_TAGS]
    if not scopes:
        scopes = ["general"]
    return [
        ExtractionRule(
            scope=scope,
            threshold=rule.amount_max,
            mode=mode,
            co_signers=[] if blocked else co_signers,
            blocked=blocked,
            evidence=rule.evidence,
        )
        for scope in _ordered_unique(scopes)
    ]


def _joint_rule_ids(
    rule: AuthorityRule,
    extraction: CircularExtraction,
    id_map: dict[str, str],
) -> list[str] | None:
    resolved: list[str] = []
    for party in [rule.who, *rule.joint_with]:
        party_ids = _party_rep_ids(party, extraction, id_map)
        if not party_ids:
            return None
        resolved.extend(party_ids)
    return _ordered_unique(resolved)


def _party_rep_ids(
    party: RulePartyRef,
    extraction: CircularExtraction,
    id_map: dict[str, str],
) -> list[str] | None:
    if party.type is RulePartyType.PERSON:
        return [id_map[party.ref]] if party.ref in id_map else None
    if party.type is RulePartyType.GROUP:
        target = tr_normalize(party.ref or "")
        matches = [
            id_map[item.id]
            for item in extraction.signatories
            if item.group_code and tr_normalize(item.group_code) == target
        ]
        return matches or None
    return None


def _party_contains(
    party: RulePartyRef, signatory_id: str, group_code: str | None
) -> bool:
    if party.type is RulePartyType.PERSON:
        return party.ref == signatory_id
    return (
        party.type is RulePartyType.GROUP
        and group_code is not None
        and tr_normalize(party.ref or "") == tr_normalize(group_code)
    )


def _is_blocked(rule: AuthorityRule) -> bool:
    normalized = tr_normalize(f"{rule.scope_text} {rule.evidence.quote}")
    return any(phrase in normalized for phrase in _BLOCKED_PHRASES)


def _authority_evidence(extraction: CircularExtraction) -> AuthorityClauseEvidence:
    candidates = [
        rule
        for rule in extraction.rules
        if rule.source is not RuleSource.ANNEX and rule.evidence.quote != "UNREADABLE"
    ]
    if candidates:
        candidates.sort(
            key=lambda rule: (
                rule.partial,
                rule.source is not RuleSource.CIRCULAR,
                rule.evidence.page,
            )
        )
        selected = candidates[0].evidence
        return AuthorityClauseEvidence(
            authority_clause=selected.quote,
            page=selected.page,
        )
    for signatory in extraction.signatories:
        if signatory.evidence and signatory.evidence.quote != "UNREADABLE":
            return AuthorityClauseEvidence(
                authority_clause=signatory.evidence.quote,
                page=signatory.evidence.page,
            )
    if extraction.company.evidence:
        selected = extraction.company.evidence[0]
        return AuthorityClauseEvidence(
            authority_clause=selected.quote,
            page=selected.page,
        )
    return AuthorityClauseEvidence(authority_clause="UNREADABLE", page=1)


def _stub_outcome(
    document_id: str, source_sha256: str, stub_dir: Path
) -> PipelineOutcome:
    started = perf_counter()
    try:
        fixture = _stub_path(document_id, stub_dir)
        result = ExtractionResult.model_validate_json(fixture.read_text(encoding="utf-8"))
        result = result.model_copy(update={"document_id": document_id})
        timing = PipelineStageTiming(stage="stub", seconds=perf_counter() - started)
        return PipelineOutcome(
            result=result,
            circular=None,
            source_sha256=source_sha256,
            mode=PipelineMode.STUB,
            timings=(timing,),
            sorter_raw_responses=(),
            page_count=0,
            chunk_count=0,
            cache_hit=False,
            degraded=False,
        )
    except Exception as error:
        return _direct_degraded_outcome(
            document_id,
            source_sha256,
            PipelineMode.STUB,
            "stub",
            error,
            timings=[
                PipelineStageTiming(
                    stage="stub",
                    seconds=perf_counter() - started,
                    status=PipelineStageStatus.DEGRADED,
                    detail=_error_detail(error),
                )
            ],
        )


def _stub_path(document_id: str, stub_dir: Path) -> Path:
    token = tr_normalize(document_id)
    if "case2" in token or token.endswith("02"):
        case = 2
    elif "case3" in token or token.endswith("03"):
        case = 3
    elif "case4" in token or token.endswith("04"):
        case = 4
    else:
        case = 1
    return stub_dir / f"case{case}.json"


def _read_cache(
    cache_dir: Path, source_sha256: str
) -> tuple[ExtractionCacheEntry | None, Exception | None]:
    path = cache_dir / f"{source_sha256}.json"
    try:
        raw = path.read_text(encoding="utf-8")
        entry = ExtractionCacheEntry.model_validate_json(raw)
        if entry.source_sha256 != source_sha256:
            raise ValueError("cache sha256 does not match its filename")
        return entry, None
    except FileNotFoundError as error:
        return None, error
    except (OSError, ValidationError, ValueError, json.JSONDecodeError) as error:
        return None, error


def _outcome_from_cache(
    entry: ExtractionCacheEntry,
    document_id: str,
    mode: PipelineMode,
) -> PipelineOutcome:
    result = entry.result.model_copy(update={"document_id": document_id})
    circular = (
        entry.circular.model_copy(update={"document_id": document_id})
        if entry.circular
        else None
    )
    return PipelineOutcome(
        result=result,
        circular=circular,
        source_sha256=entry.source_sha256,
        mode=mode,
        timings=tuple(entry.timings),
        sorter_raw_responses=tuple(entry.sorter_raw_responses),
        page_count=entry.page_count,
        chunk_count=entry.chunk_count,
        cache_hit=True,
        degraded=entry.degraded,
    )


def _write_outcome_cache(outcome: PipelineOutcome, cache_dir: Path) -> PipelineOutcome:
    entry = ExtractionCacheEntry(
        source_sha256=outcome.source_sha256,
        result=outcome.result,
        circular=outcome.circular,
        timings=list(outcome.timings),
        sorter_raw_responses=list(outcome.sorter_raw_responses),
        page_count=outcome.page_count,
        chunk_count=outcome.chunk_count,
        degraded=outcome.degraded,
    )
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / f"{outcome.source_sha256}.json"
        temporary = target.with_suffix(f".{uuid4().hex}.tmp")
        temporary.write_text(
            entry.model_dump_json(by_alias=True),
            encoding="utf-8",
        )
        temporary.replace(target)
    except OSError:
        # Cache is stage insurance, never a reason to discard a valid extraction.
        pass
    return outcome


def _direct_degraded_outcome(
    document_id: str,
    source_sha256: str,
    mode: PipelineMode,
    stage: str,
    error: Exception,
    *,
    timings: Sequence[PipelineStageTiming] = (),
) -> PipelineOutcome:
    field = f"pipeline.{stage}"
    result = _degraded_result(document_id, [field])
    recorded = list(timings)
    if not recorded:
        recorded.append(
            PipelineStageTiming(
                stage=stage,
                seconds=0,
                status=PipelineStageStatus.DEGRADED,
                detail=_error_detail(error),
            )
        )
    return PipelineOutcome(
        result=result,
        circular=None,
        source_sha256=source_sha256,
        mode=mode,
        timings=tuple(recorded),
        sorter_raw_responses=(),
        page_count=0,
        chunk_count=0,
        cache_hit=False,
        degraded=True,
    )


def _degraded_result(
    document_id: str,
    fields: Sequence[str],
    circular: CircularExtraction | None = None,
) -> ExtractionResult:
    company_name = circular.company.legal_name if circular else "UNREADABLE"
    evidence = _authority_evidence(circular) if circular else AuthorityClauseEvidence(
        authority_clause="UNREADABLE", page=1
    )
    return ExtractionResult(
        document_id=document_id,
        company=ExtractionCompany(name=company_name or "UNREADABLE"),
        notary=ExtractionNotary(),
        representatives=[],
        fields_needing_review=_ordered_unique(fields),
        evidence=evidence,
        rules=[],
    )


def _empty_circular(
    document_id: str,
    page_map: PageMap,
    chunk_results: Sequence[ChunkExtractionResult],
) -> CircularExtraction:
    return CircularExtraction(
        document_id=document_id,
        company=CompanyRecord(legal_name=page_map.company_name_line or "UNREADABLE"),
        page_map=page_map,
        raw_chunks=[result.model_dump(mode="json") for result in chunk_results],
    )


def _unknown_page_map(page_count: int, error: Exception) -> PageMap:
    count = max(1, page_count)
    return PageMap(
        structure_hints=[f"pipeline sorter failure: {_error_detail(error)}"],
        pages=[
            PageClassification(page=page, labels=[PageLabel.OTHER_UNKNOWN])
            for page in range(1, count + 1)
        ],
    )


def _pipeline_flag(stage: str, error: Exception) -> ProvenanceFlag:
    return ProvenanceFlag(
        severity=FlagSeverity.SERIOUS,
        check_name="pipeline_stage",
        message=f"{stage} aşaması tamamlanamadı; insan incelemesi gerekiyor.",
        field_path=f"pipeline.{stage}",
        anomaly_code="PIPELINE_STAGE_FAILED",
    )


def _timing(
    timings: list[PipelineStageTiming],
    stage: str,
    started: float,
    error: Exception | None = None,
) -> None:
    timings.append(
        PipelineStageTiming(
            stage=stage,
            seconds=perf_counter() - started,
            status=(
                PipelineStageStatus.DEGRADED if error else PipelineStageStatus.OK
            ),
            detail=_error_detail(error) if error else None,
        )
    )


def _resolve_mode(value: PipelineMode | str | None) -> PipelineMode:
    raw = value.value if isinstance(value, PipelineMode) else value
    return PipelineMode((raw or os.getenv("AI_MODE", PipelineMode.LIVE.value)).lower())


def _cache_enabled(value: bool | None) -> bool:
    if value is not None:
        return value
    return os.getenv("EXTRACTION_CACHE", "on").strip().lower() in _CACHE_ON


def _error_detail(error: Exception) -> str:
    # Diagnostics may run on real circulars. Exception strings from schema validation can echo
    # extracted names or quotes, while the private raw cache already retains the full evidence.
    return type(error).__name__


def _ordered_unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _unique_flags(values: Iterable[ProvenanceFlag]) -> list[ProvenanceFlag]:
    result: list[ProvenanceFlag] = []
    keys: set[tuple[str, str, str | None]] = set()
    for flag in values:
        key = (flag.check_name, flag.field_path, flag.anomaly_code)
        if key not in keys:
            keys.add(key)
            result.append(flag)
    return result
