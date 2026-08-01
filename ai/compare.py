# ai/compare.py
"""The nine deterministic checks comparing an application, its document, and the registry."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from types import MappingProxyType

from pydantic import ValidationError

if __package__:
    from .schema import (
        CHECK_IDS,
        AnalyzeRequest,
        ApplicationRecord,
        CheckId,
        CheckItem,
        CheckReport,
        CheckStatus,
        CheckVerdict,
        ExtractionResult,
        RegistryCompany,
        RegistryRepresentative,
        Representative,
        SignatureMode,
    )
    from .turkish import company_equal, digits_only, masked_id_equal, name_equal
else:  # uvicorn main:app started from inside ai/
    from schema import (
        CHECK_IDS,
        AnalyzeRequest,
        ApplicationRecord,
        CheckId,
        CheckItem,
        CheckReport,
        CheckStatus,
        CheckVerdict,
        ExtractionResult,
        RegistryCompany,
        RegistryRepresentative,
        Representative,
        SignatureMode,
    )
    from turkish import company_equal, digits_only, masked_id_equal, name_equal

# Neutral noun phrases: the same title has to be honest above a green, an amber, and a red row.
CHECK_TITLES = MappingProxyType(
    {
        CheckId.COMPANY_NAME_MATCH: "Şirket unvanı",
        CheckId.TAX_NUMBER_MATCH: "Vergi kimlik numarası",
        CheckId.MERSIS_NUMBER_MATCH: "MERSİS numarası",
        CheckId.APPLICANT_IN_DOCUMENT: "Başvuru sahibi belgede",
        CheckId.IDENTITY_MATCH: "Kimlik doğrulaması",
        CheckId.AUTHORITY_MODE: "İmza yetkisi türü",
        CheckId.REGISTRY_STATUS: "Sicil durumu",
        CheckId.REGISTRY_REPRESENTATIVE_MATCH: "Sicilde temsil yetkisi",
        CheckId.DOCUMENT_VALIDITY: "Belge geçerliliği",
    }
)

# Only these two checks read the registry; any other red means the document itself is wrong.
REGISTRY_CHECK_IDS = frozenset({CheckId.REGISTRY_STATUS, CheckId.REGISTRY_REPRESENTATIVE_MATCH})

# Amber means "a co-signer is required" — the one non-green outcome that is not a failure. Every
# other check is green or red, so unreadable input can never be dressed up as a soft warning.
AMBER_CHECKS = frozenset({CheckId.AUTHORITY_MODE})

REGISTRY_SOURCE = "simüle MERSİS"
ACTIVE = "ACTIVE"


@dataclass(frozen=True)
class _Context:
    """Everything the nine checks need, resolved once so no check repeats a lookup."""

    application: ApplicationRecord
    extraction: ExtractionResult
    registry_company: RegistryCompany | None
    representative: Representative | None
    registry_rep: RegistryRepresentative | None
    reference_date: Date


def analyze(request: AnalyzeRequest) -> CheckReport:
    """Runs all nine checks in the frozen order and derives the verdict from their statuses."""

    context = _resolve(request)
    checks = [builder(context) for builder in _BUILDERS]
    statuses = {check.id: check.status for check in checks}
    return CheckReport(verdict=verdict_from_statuses(statuses), checks=checks)


def verdict_from_statuses(statuses: dict[CheckId, CheckStatus]) -> CheckVerdict:
    """Frozen priority: MISMATCH > REGISTRY_CONFLICT > CO_SIGNER_REQUIRED > READY."""

    reds = {check_id for check_id, status in statuses.items() if status is CheckStatus.RED}
    if reds - REGISTRY_CHECK_IDS:
        return CheckVerdict.MISMATCH
    if reds:
        return CheckVerdict.REGISTRY_CONFLICT
    if any(status is CheckStatus.AMBER for status in statuses.values()):
        return CheckVerdict.CO_SIGNER_REQUIRED
    return CheckVerdict.READY


def degraded_report(error: ValidationError) -> CheckReport:
    """Turns an unusable request into nine red rows: the screen never loses its nine checks."""

    paths = {".".join(str(part) for part in issue["loc"]) for issue in error.errors()}
    fields = ", ".join(sorted(paths)) or "bilinmiyor"
    reason = f"Girdi doğrulanamadı, karşılaştırma yapılamadı. Sorunlu alanlar: {fields}."
    return CheckReport(
        verdict=CheckVerdict.MISMATCH,
        checks=[
            _check(check_id, CheckStatus.RED, reason, {"Hatalı alanlar": fields})
            for check_id in CHECK_IDS
        ],
    )


def _resolve(request: AnalyzeRequest) -> _Context:
    application = request.application
    company = _registry_company(request.registry, application.mersis)
    representative = _find_by_name(request.extraction.representatives, application.applicant_name)
    registry_rep = _find_by_name(company.reps if company else [], application.applicant_name)
    return _Context(
        application=application,
        extraction=request.extraction,
        registry_company=company,
        representative=representative,
        registry_rep=registry_rep,
        reference_date=request.as_of or Date.today(),
    )


def _registry_company(
    registry: dict[str, RegistryCompany], mersis: str | None
) -> RegistryCompany | None:
    """Looks up by digits, so a MERSİS number typed with spaces still finds its company."""

    if not mersis:
        return None
    wanted = digits_only(mersis)
    for key, company in registry.items():
        if digits_only(key) == wanted:
            return company
    return None


def _find_by_name(people, name: str | None):
    if not name:
        return None
    return next((person for person in people if name_equal(person.name, name)), None)


def _check(
    check_id: CheckId,
    status: CheckStatus,
    reason: str,
    evidence: dict[str, str | int | float | bool | None] | None = None,
) -> CheckItem:
    return CheckItem(
        id=check_id,
        status=status,
        title=CHECK_TITLES[check_id],
        reason=reason,
        evidence=evidence or {},
    )


def _company_name_match(context: _Context) -> CheckItem:
    applied = context.application.company_name
    printed = context.extraction.company.name
    evidence = {"Başvuru": applied, "Belge": printed}

    if not applied or not printed:
        return _check(
            CheckId.COMPANY_NAME_MATCH,
            CheckStatus.RED,
            "Unvan karşılaştırılamadı: taraflardan birinde şirket unvanı yok.",
            evidence,
        )
    if company_equal(applied, printed):
        return _check(
            CheckId.COMPANY_NAME_MATCH,
            CheckStatus.GREEN,
            "Başvurudaki unvan ile belgedeki unvan aynı şirketi gösteriyor.",
            evidence,
        )
    return _check(
        CheckId.COMPANY_NAME_MATCH,
        CheckStatus.RED,
        "Başvuru ve belge farklı şirketlere ait.",
        evidence,
    )


def _number_match(context: _Context, check_id: CheckId, label: str) -> CheckItem:
    if check_id is CheckId.TAX_NUMBER_MATCH:
        applied, printed = context.application.tax_number, context.extraction.company.tax_number
    else:
        applied, printed = context.application.mersis, context.extraction.company.mersis_number
    evidence = {"Başvuru": applied, "Belge": printed}

    if not applied or not printed:
        return _check(
            check_id, CheckStatus.RED, f"{label} karşılaştırılamadı: taraflardan birinde yok.", evidence
        )
    if digits_only(applied) == digits_only(printed):
        return _check(check_id, CheckStatus.GREEN, f"{label} birebir aynı.", evidence)
    return _check(check_id, CheckStatus.RED, f"{label} başvuru ile belgede farklı.", evidence)


def _tax_number_match(context: _Context) -> CheckItem:
    return _number_match(context, CheckId.TAX_NUMBER_MATCH, "Vergi kimlik numarası")


def _mersis_number_match(context: _Context) -> CheckItem:
    return _number_match(context, CheckId.MERSIS_NUMBER_MATCH, "MERSİS numarası")


def _applicant_in_document(context: _Context) -> CheckItem:
    applicant = context.application.applicant_name
    listed = ", ".join(person.name for person in context.extraction.representatives)
    evidence = {"Başvuru sahibi": applicant, "Belgedeki yetkililer": listed or None}

    if not applicant:
        return _check(
            CheckId.APPLICANT_IN_DOCUMENT,
            CheckStatus.RED,
            "Başvuruda başvuru sahibinin adı yok.",
            evidence,
        )
    if context.representative is None:
        # Deliberately red, never a fuzzy amber: a name that is not in the document is not a doubt.
        return _check(
            CheckId.APPLICANT_IN_DOCUMENT,
            CheckStatus.RED,
            f"{applicant} belgedeki yetkililer arasında yer almıyor.",
            evidence,
        )
    return _check(
        CheckId.APPLICANT_IN_DOCUMENT,
        CheckStatus.GREEN,
        f"{applicant} belgede temsile yetkili olarak yer alıyor.",
        evidence,
    )


def _identity_match(context: _Context) -> CheckItem:
    applied = context.application.applicant_tckn
    representative = context.representative
    printed = representative.national_id if representative else None
    evidence = {"Başvuru": applied, "Belge": printed}

    if representative is None:
        return _check(
            CheckId.IDENTITY_MATCH,
            CheckStatus.RED,
            "Başvuru sahibi belgede bulunmadığı için kimlik karşılaştırması yapılamadı.",
            evidence,
        )
    if not applied or not printed:
        return _check(
            CheckId.IDENTITY_MATCH,
            CheckStatus.RED,
            "Kimlik numarası karşılaştırılamadı: taraflardan birinde maskeli numara yok.",
            evidence,
        )
    if masked_id_equal(applied, printed):
        return _check(
            CheckId.IDENTITY_MATCH,
            CheckStatus.GREEN,
            "Ad eşleşmesini maskeli T.C. kimlik numarası da doğruluyor.",
            evidence,
        )
    return _check(
        CheckId.IDENTITY_MATCH,
        CheckStatus.RED,
        "Ad eşleşti fakat maskeli kimlik numaraları farklı.",
        evidence,
    )


def _authority_mode(context: _Context) -> CheckItem:
    representative = context.representative
    if representative is None:
        return _check(
            CheckId.AUTHORITY_MODE,
            CheckStatus.RED,
            "Başvuru sahibi belgede yer almadığı için imza yetkisi türü belirlenemedi.",
            {"Başvuru sahibi": context.application.applicant_name},
        )

    co_signers = ", ".join(representative.co_signers)
    evidence = {
        "İmza türü": representative.mode.value,
        "Eş imzacılar": co_signers or None,
        "Limit": _format_amount(representative.limits) if representative.limits else None,
    }

    if representative.mode is SignatureMode.JOINT:
        reason = (
            f"{representative.name} tek başına imzalayamaz; {co_signers} ile müşterek imza gerekiyor."
            if co_signers
            else f"{representative.name} müşterek imza yetkisine sahip, eş imzacı belgede adlandırılmamış."
        )
        return _check(CheckId.AUTHORITY_MODE, CheckStatus.AMBER, reason, evidence)

    reason = f"{representative.name} şirketi münferiden temsile yetkili."
    if representative.limits:
        reason = (
            f"{representative.name} {_format_amount(representative.limits)} tutarına kadar "
            "münferiden temsile yetkili."
        )
    return _check(CheckId.AUTHORITY_MODE, CheckStatus.GREEN, reason, evidence)


def _registry_status(context: _Context) -> CheckItem:
    company = context.registry_company
    mersis = context.application.mersis
    evidence = {
        "Sicil kaydı": mersis,
        "Durum": company.status if company else None,
        "Kaynak": REGISTRY_SOURCE,
    }

    if company is None:
        return _check(
            CheckId.REGISTRY_STATUS,
            CheckStatus.RED,
            "MERSİS numarası sicilde bulunamadı.",
            evidence,
        )
    if company.status.upper() != ACTIVE:
        return _check(
            CheckId.REGISTRY_STATUS,
            CheckStatus.RED,
            f"Şirketin sicil durumu faal değil: {company.status}.",
            evidence,
        )
    return _check(
        CheckId.REGISTRY_STATUS, CheckStatus.GREEN, "Şirket sicilde faal görünüyor.", evidence
    )


def _registry_representative_match(context: _Context) -> CheckItem:
    check_id = CheckId.REGISTRY_REPRESENTATIVE_MATCH
    applicant = context.application.applicant_name
    registry_rep = context.registry_rep
    evidence = {
        "Başvuru sahibi": applicant,
        "Sicil durumu": registry_rep.status if registry_rep else None,
        "Kaynak": REGISTRY_SOURCE,
    }

    if context.registry_company is None:
        return _check(
            check_id, CheckStatus.RED, "Şirket sicilde bulunamadığı için temsilci doğrulanamadı.", evidence
        )
    if registry_rep is None:
        return _check(
            check_id, CheckStatus.RED, f"{applicant} sicilde temsilci olarak görünmüyor.", evidence
        )
    if registry_rep.status.upper() != ACTIVE:
        return _check(
            check_id,
            CheckStatus.RED,
            f"{applicant} sicilde kayıtlı ancak temsil yetkisi düşmüş ({registry_rep.status}).",
            evidence,
        )
    if (
        registry_rep.tckn
        and context.application.applicant_tckn
        and not masked_id_equal(registry_rep.tckn, context.application.applicant_tckn)
    ):
        return _check(
            check_id,
            CheckStatus.RED,
            "Sicildeki maskeli kimlik numarası başvurudakiyle uyuşmuyor.",
            evidence | {"Sicil kimlik": registry_rep.tckn},
        )
    return _check(
        check_id, CheckStatus.GREEN, f"{applicant} sicilde aktif temsilci olarak görünüyor.", evidence
    )


def _document_validity(context: _Context) -> CheckItem:
    valid_until = context.extraction.valid_until
    evidence = {
        "Geçerlilik": _format_date(valid_until),
        "Kontrol tarihi": _format_date(context.reference_date),
    }

    if valid_until is None:
        return _check(
            CheckId.DOCUMENT_VALIDITY,
            CheckStatus.RED,
            "Belgede geçerlilik tarihi bulunamadı.",
            evidence,
        )
    if valid_until < context.reference_date:
        return _check(
            CheckId.DOCUMENT_VALIDITY,
            CheckStatus.RED,
            f"Belgenin geçerliliği {_format_date(valid_until)} tarihinde sona ermiş.",
            evidence,
        )
    return _check(
        CheckId.DOCUMENT_VALIDITY,
        CheckStatus.GREEN,
        f"Belge {_format_date(valid_until)} tarihine kadar geçerli.",
        evidence,
    )


def _format_date(value: Date | None) -> str | None:
    return value.strftime("%d.%m.%Y") if value else None


def _format_amount(value_kurus: int) -> str:
    """Formats integer kuruş (1 TL = 100 kuruş) as a Turkish-style TL amount."""

    tl, kurus_remainder = divmod(value_kurus, 100)
    integer = f"{tl:,}".replace(",", ".")
    return f"{integer},{kurus_remainder:02d} TL"


# Order is the frozen CheckId order; CheckReport rejects any other sequence.
_BUILDERS = (
    _company_name_match,
    _tax_number_match,
    _mersis_number_match,
    _applicant_in_document,
    _identity_match,
    _authority_mode,
    _registry_status,
    _registry_representative_match,
    _document_validity,
)
