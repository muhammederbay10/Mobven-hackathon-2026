"""Guards on the Phase 0 contract freeze.

IMPLEMENTATION_PLAN.md section 18: "An agent may not silently rename enum
values, change response shapes, add an authorized person, broaden an authority
rule, bypass attestations, or turn a simulated integration into an unlabeled
fake."  These tests are what makes "silently" impossible: every frozen value is
spelled out here, so a rename shows up as a failing test and a deliberate
contract change has to be an explicit, reviewed edit in three places at once.

No network access. No database. Pure contract assertions.
"""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from api import schemas as s
from api.tests.conftest import REPO_ROOT

TYPES_TS = REPO_ROOT / "web" / "lib" / "types.ts"


# ---------------------------------------------------------------------------
# The nine checks — plan section 6
# ---------------------------------------------------------------------------


def test_check_ids_are_the_frozen_nine_in_order() -> None:
    assert s.CHECK_IDS == (
        "company_name_match",
        "tax_number_match",
        "mersis_number_match",
        "applicant_in_document",
        "identity_match",
        "authority_mode",
        "registry_company_status",
        "registry_representative_status",
        "document_validity",
    )
    assert len(s.CHECK_IDS) == 9
    assert len(set(s.CHECK_IDS)) == 9


# ---------------------------------------------------------------------------
# Enum membership — plan sections 5, 7
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("enum_cls", "expected"),
    [
        (s.Confidence, {"HIGH", "MEDIUM", "LOW"}),
        (s.ReviewSeverity, {"INFO", "WARNING", "ERROR"}),
        (s.AuthorityMode, {"SOLE", "JOINT", "LIMITED", "UNKNOWN"}),
        (s.TransactionSubject, {"GENERAL", "CREDIT", "REAL_ESTATE"}),
        (s.CheckStatus, {"GREEN", "AMBER", "RED"}),
        (
            s.OnboardingVerdict,
            {"READY", "CO_SIGNER_REQUIRED", "MISMATCH", "REGISTRY_CONFLICT"},
        ),
        (s.CheckSourceKind, {"APPLICATION", "IDENTITY", "DOCUMENT", "REGISTRY"}),
        (s.TransactionVerdict, {"ALLOWED", "PENDING_COSIGN", "DENIED"}),
        (
            s.ApplicationStatus,
            {
                "DRAFT",
                "IDENTITY_VERIFIED",
                "DOCUMENT_SCANNED",
                "ANALYZING",
                "ANALYZED",
                "APPROVED",
                "DOC_REQUESTED",
                "ESCALATED",
                "ANALYSIS_FAILED",
            },
        ),
        (s.TransactionStatus, {"REQUESTED", "ALLOWED", "PENDING_COSIGN", "DENIED"}),
        (s.AuthorityRecordStatus, {"ACTIVE", "SUSPENDED"}),
        (s.RegistryCompanyStatus, {"ACTIVE", "INACTIVE"}),
        (s.RegistryRepresentativeStatus, {"ACTIVE", "REMOVED"}),
        (s.ApplicationDecisionAction, {"approve", "request_document", "escalate"}),
    ],
)
def test_enum_members_are_frozen(enum_cls: type, expected: set[str]) -> None:
    assert {member.value for member in enum_cls} == expected


def test_plan_named_error_codes_exist() -> None:
    # Named directly in plan sections 5.7, 7.2 and 8.7.
    for code in ("DOCUMENT_REQUIRED", "INVALID_STATE_TRANSITION", "STALE_CORRECTION"):
        assert code in {c.value for c in s.ErrorCode}


# ---------------------------------------------------------------------------
# State machines — plan sections 7.2 and 7.3
# ---------------------------------------------------------------------------


def test_application_transitions_match_the_plan() -> None:
    A = s.ApplicationStatus
    assert s.APPLICATION_TRANSITIONS[A.DRAFT] == frozenset({A.IDENTITY_VERIFIED})
    assert s.APPLICATION_TRANSITIONS[A.IDENTITY_VERIFIED] == frozenset({A.DOCUMENT_SCANNED})
    assert s.APPLICATION_TRANSITIONS[A.DOCUMENT_SCANNED] == frozenset({A.ANALYZING})
    assert s.APPLICATION_TRANSITIONS[A.ANALYZING] == frozenset({A.ANALYZED, A.ANALYSIS_FAILED})
    assert s.APPLICATION_TRANSITIONS[A.ANALYSIS_FAILED] == frozenset({A.ANALYZING})
    assert s.APPLICATION_TRANSITIONS[A.ANALYZED] == frozenset(
        {A.APPROVED, A.DOC_REQUESTED, A.ESCALATED, A.ANALYZING}
    )
    # Every status is described, and terminal states really are terminal.
    assert set(s.APPLICATION_TRANSITIONS) == set(A)
    for terminal in (A.APPROVED, A.DOC_REQUESTED, A.ESCALATED):
        assert s.APPLICATION_TRANSITIONS[terminal] == frozenset()


def test_transaction_transitions_match_the_plan() -> None:
    T = s.TransactionStatus
    assert s.TRANSACTION_TRANSITIONS[T.REQUESTED] == frozenset(
        {T.ALLOWED, T.PENDING_COSIGN, T.DENIED}
    )
    assert s.TRANSACTION_TRANSITIONS[T.PENDING_COSIGN] == frozenset({T.ALLOWED, T.DENIED})
    assert s.TRANSACTION_TRANSITIONS[T.ALLOWED] == frozenset()
    assert s.TRANSACTION_TRANSITIONS[T.DENIED] == frozenset()


def test_approval_matrix_matches_gap_07() -> None:
    V = s.OnboardingVerdict
    assert s.APPROVABLE_VERDICTS == frozenset({V.READY, V.CO_SIGNER_REQUIRED})
    assert s.VERDICTS_REQUIRING_OVERRIDE_JUSTIFICATION == frozenset({V.CO_SIGNER_REQUIRED})
    # Red verdicts are never approvable in the MVP.
    assert V.MISMATCH not in s.APPROVABLE_VERDICTS
    assert V.REGISTRY_CONFLICT not in s.APPROVABLE_VERDICTS


# ---------------------------------------------------------------------------
# Identifier formats — plan sections 8.7, 14 and GAP-08 / GAP-09 / GAP-12
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["1234567890", "9876543210"])
def test_tax_number_accepts_ten_digits(value: str) -> None:
    assert re.match(s.TAX_NUMBER_PATTERN, value)


@pytest.mark.parametrize("value", ["123456789", "12345678901", "12345 6789", "abcdefghij"])
def test_tax_number_rejects_everything_else(value: str) -> None:
    assert not re.match(s.TAX_NUMBER_PATTERN, value)


@pytest.mark.parametrize("value", ["0123456789000017", "0987654321000023"])
def test_mersis_accepts_sixteen_digits(value: str) -> None:
    assert re.match(s.MERSIS_PATTERN, value)


@pytest.mark.parametrize("value", ["012345678900001", "01234567890000178"])
def test_mersis_rejects_wrong_length(value: str) -> None:
    assert not re.match(s.MERSIS_PATTERN, value)


@pytest.mark.parametrize("value", ["123******01", "987******45", "456******07", "555******22"])
def test_masked_tckn_accepts_the_fixed_cast_format(value: str) -> None:
    """GAP-08: the four demo people, in the one masked format allowed anywhere."""
    assert re.match(s.TCKN_MASKED_PATTERN, value)


@pytest.mark.parametrize(
    "value",
    [
        "12345678901",  # plan section 14: a plausible unmasked TCKN must be rejected
        "123*****01",  # five stars
        "123*******01",  # seven stars
        "12******301",
        "***********",
    ],
)
def test_masked_tckn_rejects_unmasked_and_malformed(value: str) -> None:
    assert not re.match(s.TCKN_MASKED_PATTERN, value)


@pytest.mark.parametrize("value", ["rep_abc_ali", "rep_abc_ayse", "rep_zeta_kemal"])
def test_registry_rep_ids_use_the_stable_id_form(value: str) -> None:
    """GAP-09: registry representatives are addressed by stable ID, never by name."""
    assert re.match(s.REGISTRY_REP_ID_PATTERN, value)


@pytest.mark.parametrize("value", ["Ali Yılmaz", "rep-1", "REP_ABC_ALI", "ali"])
def test_registry_rep_ids_reject_names_and_extraction_ids(value: str) -> None:
    assert not re.match(s.REGISTRY_REP_ID_PATTERN, value)


def test_branch_actor_is_the_fixed_constant() -> None:
    assert s.BRANCH_ACTOR == "branch_user:kozyatagi01"


def test_currency_is_fixed_try() -> None:
    assert s.CURRENCY == "TRY"


def test_amount_minor_is_integer_kurus() -> None:
    """GAP-12: 500,000 TL is 50000000 minor units. No floating point money."""
    rule = s.AuthorityRule(
        id="r1",
        subject=s.TransactionSubject.GENERAL,
        currency="TRY",
        min_amount_minor=0,
        max_amount_minor=50_000_000,
        required_signers=["rep-1"],
        minimum_signature_count=1,
        allowed=True,
        valid_from=None,
        valid_until=None,
        evidence=[],
    )
    assert rule.max_amount_minor == 50_000_000
    assert isinstance(rule.max_amount_minor, int)

    with pytest.raises(ValidationError):
        s.AuthorizeTransactionRequest(
            mersis="0123456789000017",
            subject=s.TransactionSubject.GENERAL,
            currency="TRY",
            amount_minor=-1,
            initiator="person-1",
        )
    with pytest.raises(ValidationError):
        s.AuthorizeTransactionRequest(
            mersis="0123456789000017",
            subject=s.TransactionSubject.GENERAL,
            currency="TRY",
            amount_minor=250_000.5,  # type: ignore[arg-type]
            initiator="person-1",
        )


# ---------------------------------------------------------------------------
# Correction allowlist — plan section 8.7
# ---------------------------------------------------------------------------


def test_correction_allowlist_is_exactly_the_six_closed_decision_fields() -> None:
    assert s.CORRECTION_PATH_ALLOWLIST == (
        "company.legal_name.value",
        "company.tax_number.value",
        "company.mersis.value",
        "representatives[<source_id>].name.value",
        "representatives[<source_id>].authority_mode.value",
        "document_valid_until.value",
    )
    assert len(s.CORRECTION_PATH_ALLOWLIST) == 6


@pytest.mark.parametrize(
    "path",
    [
        "company.legal_name.value",
        "company.tax_number.value",
        "company.mersis.value",
        "representatives[rep-1].name.value",
        "representatives[rep-2].authority_mode.value",
        "document_valid_until.value",
    ],
)
def test_correction_pattern_accepts_the_allowed_paths(path: str) -> None:
    s.ExtractionCorrectionItem(field_path=path, expected_old_value=None, new_value="x")


@pytest.mark.parametrize(
    "path",
    [
        "company.trade_registry_number.value",  # not in the six
        "notary.name.value",
        "rules[0].max_amount_minor",  # broadening a rule is never a correction
        "representatives[0].name.value",  # array position, not source_id
        "representatives[Ali Yılmaz].name.value",  # display name, not source_id
        "representatives[rep-1].tckn_masked.value",
        "representatives[rep-1].name",
        "",
    ],
)
def test_correction_pattern_rejects_everything_else(path: str) -> None:
    with pytest.raises(ValidationError):
        s.ExtractionCorrectionItem(field_path=path, expected_old_value=None, new_value="x")


# ---------------------------------------------------------------------------
# Response shapes — plan sections 5.3 and 5.7
# ---------------------------------------------------------------------------


def _check(check_id: str, status: s.CheckStatus = s.CheckStatus.GREEN) -> dict[str, object]:
    return {
        "id": check_id,
        "status": status.value,
        "title": check_id,
        "reason": "kontrol edildi",
        "source_kind": "DOCUMENT",
        "evidence": [],
    }


def test_check_report_requires_all_nine_checks_in_order() -> None:
    ok = {
        "schema_version": "1.0",
        "verdict": "READY",
        "checks": [_check(cid) for cid in s.CHECK_IDS],
        "blocking_check_ids": [],
        "generated_at": "2026-08-01T10:00:00Z",
    }
    assert len(s.CheckReport.model_validate(ok).checks) == 9

    with pytest.raises(ValidationError):  # one missing
        s.CheckReport.model_validate({**ok, "checks": [_check(c) for c in s.CHECK_IDS[:8]]})

    with pytest.raises(ValidationError):  # right nine, wrong order
        reordered = list(s.CHECK_IDS)
        reordered[0], reordered[1] = reordered[1], reordered[0]
        s.CheckReport.model_validate({**ok, "checks": [_check(c) for c in reordered]})

    with pytest.raises(ValidationError):  # unknown blocking id
        s.CheckReport.model_validate({**ok, "blocking_check_ids": ["not_a_check"]})


def test_unknown_keys_are_a_reportable_contract_defect() -> None:
    """Plan section 8.8: drift is reported, never silently absorbed."""
    with pytest.raises(ValidationError):
        s.CheckReport.model_validate(
            {
                "schema_version": "1.0",
                "verdict": "READY",
                "checks": [_check(cid) for cid in s.CHECK_IDS],
                "blocking_check_ids": [],
                "generated_at": "2026-08-01T10:00:00Z",
                "confidence_score": 0.91,  # not in the contract
            }
        )


def test_error_body_matches_the_standard_shape() -> None:
    body = s.ErrorResponse.model_validate(
        {
            "error": {
                "code": "DOCUMENT_REQUIRED",
                "message": "Bu başvuru için analiz edilecek belge yok.",
                "retryable": False,
                "details": {},
                "correlation_id": "b3c1f0d2",
            }
        }
    )
    assert body.error.code is s.ErrorCode.DOCUMENT_REQUIRED
    assert set(body.model_dump()["error"]) == {
        "code",
        "message",
        "retryable",
        "details",
        "correlation_id",
    }


def test_instants_are_utc_and_dates_are_calendar_only() -> None:
    with pytest.raises(ValidationError):  # local time, no zone
        s.CheckReport.model_validate(
            {
                "schema_version": "1.0",
                "verdict": "READY",
                "checks": [_check(cid) for cid in s.CHECK_IDS],
                "blocking_check_ids": [],
                "generated_at": "2026-08-01 13:00:00",
            }
        )
    with pytest.raises(ValidationError):  # Turkish display format is a UI concern
        s.AuthorityPerson(
            id="p1",
            source_id="rep-1",
            name="Ali Yılmaz",
            tckn_masked="123******01",
            title="Müdür",
            degree="1. derece",
            valid_from="01.08.2026",
            valid_until=None,
        )


# ---------------------------------------------------------------------------
# Python <-> TypeScript mirror parity — plan section 5
# ---------------------------------------------------------------------------


def test_typescript_mirror_carries_every_frozen_literal() -> None:
    """`web/lib/types.ts` must mirror this module's JSON, member for member."""
    source = TYPES_TS.read_text(encoding="utf-8")

    enums: list[type] = [
        s.Confidence,
        s.ReviewSeverity,
        s.AuthorityMode,
        s.TransactionSubject,
        s.CheckStatus,
        s.OnboardingVerdict,
        s.CheckSourceKind,
        s.TransactionVerdict,
        s.ApplicationStatus,
        s.TransactionStatus,
        s.AuthorityRecordStatus,
        s.RegistryCompanyStatus,
        s.RegistryRepresentativeStatus,
        s.ApplicationDecisionAction,
        s.ErrorCode,
    ]
    missing = [
        f"{enum_cls.__name__}.{member.value}"
        for enum_cls in enums
        for member in enum_cls
        if f'"{member.value}"' not in source
    ]
    assert not missing, f"missing from web/lib/types.ts: {missing}"

    for check_id in s.CHECK_IDS:
        assert f'"{check_id}"' in source
    for path in s.CORRECTION_PATH_ALLOWLIST:
        assert f'"{path}"' in source
    assert f'"{s.BRANCH_ACTOR}"' in source
