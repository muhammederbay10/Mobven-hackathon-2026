"""Document-derived transaction authorization and co-signing (Phase 5)."""

from __future__ import annotations

from datetime import date
import secrets
import time
from collections import defaultdict
from threading import Lock

from sqlmodel import Session, select

from api.db import to_iso_instant, utc_now
from api.errors import ApiError, not_found
from api.models import AuditAction, AuditEntity, AuthorityRecord, Transaction
from api.schemas import (
    TRANSACTION_TRANSITIONS,
    AuthorizeTransactionRequest,
    CheckStatus,
    CosignTransactionRequest,
    DecisionCheck,
    ErrorCode,
    RegistryCompanyStatus,
    RegistryRepresentativeStatus,
    TransactionDecision,
    TransactionDecisionSource,
    TransactionStatus,
    TransactionVerdict,
)
from api.services import audit_service, authority_service, registry_service

_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_COSIGN_LOCKS: defaultdict[int, Lock] = defaultdict(Lock)


def authorize(
    session: Session,
    request: AuthorizeTransactionRequest,
    *,
    correlation_id: str,
) -> TransactionDecision:
    started = time.perf_counter()
    transaction = Transaction(
        mersis=request.mersis,
        subject=request.subject,
        currency=request.currency,
        amount_minor=request.amount_minor,
        initiator=request.initiator,
        status=TransactionStatus.REQUESTED,
    )
    session.add(transaction)
    session.flush()
    try:
        authority = authority_service.get_active(session, request.mersis)
    except ApiError:
        transaction.status = TransactionStatus.DENIED
        transaction.verdict = TransactionVerdict.DENIED
        transaction.latency_ms = _latency(started)
        transaction.decision = {
            "checks": [_check(CheckStatus.RED, "Aktif yetki", "Aktif yetki kaydı bulunamadı.")]
        }
        session.add(transaction)
        _audit(session, transaction, correlation_id, "NO_ACTIVE_AUTHORITY")
        session.commit()
        raise ApiError(
            ErrorCode.AUTHORITY_NOT_FOUND,
            "Aktif yetki kaydı bulunamadı; işlem reddedildi ve kaydedildi.",
            status_code=404,
            details={"transaction_id": transaction.id},
        )

    try:
        verdict, required, checks = _evaluate(request, authority)
    except registry_service.RegistryUnavailableError:
        verdict, required, checks = _deny(
            [], "Güncel sicil", "Sicil kaydı okunamadığı için işlem güvenlik gereği reddedildi."
        )
    transaction.authority_id = authority.id
    transaction.required_cosigner = required
    transaction.verdict = verdict
    transaction.status = TransactionStatus(verdict.value)
    if verdict is TransactionVerdict.ALLOWED:
        transaction.authorization_code = _new_code(session)
    transaction.latency_ms = _latency(started)
    transaction.updated_at = utc_now()
    transaction.decision = {"checks": [item.model_dump(mode="json") for item in checks]}
    session.add(transaction)
    _audit(session, transaction, correlation_id, "INITIAL_DECISION")
    session.commit()
    session.refresh(transaction)
    return decision_view(transaction, authority)


def cosign(
    session: Session,
    transaction_id: int,
    request: CosignTransactionRequest,
    *,
    correlation_id: str,
) -> TransactionDecision:
    with _COSIGN_LOCKS[transaction_id]:
        return _cosign_locked(
            session,
            transaction_id,
            request,
            correlation_id=correlation_id,
        )


def _cosign_locked(
    session: Session,
    transaction_id: int,
    request: CosignTransactionRequest,
    *,
    correlation_id: str,
) -> TransactionDecision:
    started = time.perf_counter()
    transaction = session.get(Transaction, transaction_id)
    if transaction is None:
        raise not_found("İşlem", transaction_id)
    authority = session.get(AuthorityRecord, transaction.authority_id) if transaction.authority_id else None
    if authority is None:
        raise ApiError(ErrorCode.AUTHORITY_NOT_FOUND, "İşlemin yetki kaydı bulunamadı.", status_code=404)

    if transaction.status is TransactionStatus.ALLOWED and transaction.cosigner == request.cosigner:
        return decision_view(transaction, authority)
    if transaction.status is not TransactionStatus.PENDING_COSIGN:
        raise _cosign_error("Bu işlem ikinci imza beklemiyor.")
    if request.cosigner == transaction.initiator:
        _audit_rejected_cosign(session, transaction, request.cosigner, correlation_id, "SELF_COSIGN")
        raise _cosign_error("İşlemi başlatan kişi ikinci imzayı veremez.")
    if request.cosigner != transaction.required_cosigner:
        _audit_rejected_cosign(session, transaction, request.cosigner, correlation_id, "WRONG_COSIGNER")
        raise _cosign_error("Bu kişi beklenen ikinci imza sahibi değil.")

    replay = AuthorizeTransactionRequest(
        mersis=transaction.mersis,
        subject=transaction.subject,
        currency="TRY",
        amount_minor=transaction.amount_minor,
        initiator=transaction.initiator,
    )
    try:
        verdict, required, checks = _evaluate(replay, authority)
    except registry_service.RegistryUnavailableError:
        verdict, required, checks = _deny(
            [], "Güncel sicil", "Sicil kaydı okunamadığı için işlem güvenlik gereği reddedildi."
        )
    if verdict is not TransactionVerdict.PENDING_COSIGN or required != request.cosigner:
        _transition(transaction, TransactionStatus.DENIED)
        transaction.verdict = TransactionVerdict.DENIED
        transaction.required_cosigner = None
        transaction.latency_ms = _latency(started)
        transaction.updated_at = utc_now()
        transaction.decision = {"checks": [item.model_dump(mode="json") for item in checks]}
        session.add(transaction)
        _audit(session, transaction, correlation_id, "COSIGN_REVALIDATION_FAILED", actor=request.cosigner)
        session.commit()
        return decision_view(transaction, authority)

    company = registry_service.get_company(transaction.mersis)
    current_cosigner = next(
        (item for item in (company.representatives if company else []) if item.id == request.cosigner),
        None,
    )
    if current_cosigner is None or current_cosigner.status is not RegistryRepresentativeStatus.ACTIVE:
        _transition(transaction, TransactionStatus.DENIED)
        transaction.verdict = TransactionVerdict.DENIED
        checks.append(_check(CheckStatus.RED, "İkinci imza", "İkinci imza sahibi sicilde aktif değil."))
    else:
        _transition(transaction, TransactionStatus.ALLOWED)
        transaction.verdict = TransactionVerdict.ALLOWED
        transaction.cosigner = request.cosigner
        transaction.authorization_code = transaction.authorization_code or _new_code(session)
        checks.append(_check(CheckStatus.GREEN, "İkinci imza", "Gerekli ikinci imza doğrulandı."))
    transaction.latency_ms = _latency(started)
    transaction.updated_at = utc_now()
    transaction.decision = {"checks": [item.model_dump(mode="json") for item in checks]}
    session.add(transaction)
    _audit(session, transaction, correlation_id, "COSIGN_COMPLETED", actor=request.cosigner)
    session.commit()
    session.refresh(transaction)
    return decision_view(transaction, authority)


def history(session: Session, mersis: str) -> list[TransactionDecision]:
    rows = session.exec(
        select(Transaction).where(Transaction.mersis == mersis).order_by(Transaction.id.desc())
    ).all()
    results: list[TransactionDecision] = []
    for row in rows:
        if row.authority_id is None:
            continue
        authority = session.get(AuthorityRecord, row.authority_id)
        if authority is not None and row.verdict is not None:
            results.append(decision_view(row, authority))
    return results


def _evaluate(
    request: AuthorizeTransactionRequest, authority: AuthorityRecord
) -> tuple[TransactionVerdict, str | None, list[DecisionCheck]]:
    checks: list[DecisionCheck] = []
    if authority.status.value != "ACTIVE":
        return _deny(checks, "Aktif yetki", "Yetki kaydı aktif değil.")
    if authority.valid_until and authority.valid_until < date.today().isoformat():
        return _deny(checks, "Yetki geçerliliği", "Yetki kaydının süresi dolmuş.")
    initiators = [person for person in authority.persons if person.get("id") == request.initiator]
    if len(initiators) != 1:
        return _deny(checks, "İşlemi başlatan", "Yetkili kişi tekil olarak çözümlenemedi.")
    initiator = initiators[0]
    company = registry_service.get_company(request.mersis)
    if company is None or company.status is not RegistryCompanyStatus.ACTIVE:
        return _deny(checks, "Güncel sicil", "Şirket güncel sicilde aktif değil.")
    registry_people = [item for item in company.representatives if item.id == request.initiator]
    if len(registry_people) != 1 or registry_people[0].status is not RegistryRepresentativeStatus.ACTIVE:
        return _deny(checks, "Güncel sicil", "İşlemi başlatan kişi güncel sicilde aktif değil.")
    checks.append(_check(CheckStatus.GREEN, "Güncel sicil", "Şirket ve işlemi başlatan kişi aktif."))

    subject = request.subject.value.lower()
    rules = [rule for rule in authority.rules if str(rule.get("scope", "")).lower() == subject]
    blocked = next((rule for rule in rules if rule.get("blocked") is True), None)
    if blocked is not None:
        return _deny(checks, "Yetki kuralı", "Bu işlem konusu belge tarafından açıkça engellenmiş.")
    applicable = [
        rule
        for rule in rules
        if not rule.get("blocked")
        and (rule.get("threshold") is None or request.amount_minor <= int(rule["threshold"]))
    ]
    applicable.sort(key=lambda item: (item.get("threshold") is None, item.get("threshold") or 0))
    if not applicable:
        return _deny(checks, "Yetki kuralı", "Tutar ve işlem konusu için yetki kuralı bulunamadı.")
    rule = applicable[0]
    source_id = initiator.get("source_id")
    signers = [str(value) for value in rule.get("coSigners", [])]

    mode = rule.get("mode")
    if mode == "SOLE":
        limit = initiator.get("limits")
        if initiator.get("mode") != "SOLE" or (limit is not None and request.amount_minor > int(limit)):
            return _deny(checks, "Münferit limit", "Kişinin münferit işlem limiti yetersiz.")
        checks.append(_check(CheckStatus.GREEN, "Yetki kuralı", "Münferit yetki ve tutar limiti uygun."))
        return TransactionVerdict.ALLOWED, None, checks
    if mode == "JOINT":
        if source_id not in signers:
            return _deny(
                checks,
                "Yetki kuralı",
                "İşlemi başlatan kişi seçilen müşterek kuralın imzacıları arasında değil.",
            )
        other_source_ids = [item for item in signers if item != source_id]
        candidates = [
            person
            for person in authority.persons
            if person.get("source_id") in other_source_ids
            and any(
                registry_person.id == person.get("id")
                and registry_person.status is RegistryRepresentativeStatus.ACTIVE
                for registry_person in company.representatives
            )
        ]
        if len(candidates) != 1:
            return _deny(checks, "Müşterek imza", "Kuralı tamamlayacak tek bir aktif ikinci imzacı bulunamadı.")
        required = str(candidates[0]["id"])
        checks.append(_check(CheckStatus.AMBER, "Müşterek imza", "İşlem ikinci imza bekliyor."))
        return TransactionVerdict.PENDING_COSIGN, required, checks
    return _deny(checks, "Yetki kuralı", "Desteklenmeyen imza şekli güvenlik gereği reddedildi.")


def decision_view(transaction: Transaction, authority: AuthorityRecord) -> TransactionDecision:
    checks = [DecisionCheck.model_validate(item) for item in transaction.decision.get("checks", [])]
    return TransactionDecision(
        transaction_id=transaction.id,
        verdict=transaction.verdict,
        required_cosigner=transaction.required_cosigner,
        checks=checks,
        authorization_code=transaction.authorization_code,
        latency_ms=transaction.latency_ms,
        source=TransactionDecisionSource(
            authority_id=authority.id,
            document_id=authority.source_document_id,
            verified_at=to_iso_instant(authority.verified_at),
            channel="BRANCH_ORIGINAL_SEEN",
        ),
    )


def _deny(
    checks: list[DecisionCheck], title: str, reason: str
) -> tuple[TransactionVerdict, None, list[DecisionCheck]]:
    checks.append(_check(CheckStatus.RED, title, reason))
    return TransactionVerdict.DENIED, None, checks


def _check(status: CheckStatus, title: str, reason: str) -> DecisionCheck:
    return DecisionCheck(status=status, title=title, reason=reason)


def _transition(transaction: Transaction, target: TransactionStatus) -> None:
    if target not in TRANSACTION_TRANSITIONS[transaction.status]:
        raise _cosign_error("İşlem durumu bu geçişe izin vermiyor.")
    transaction.status = target


def _new_code(session: Session) -> str:
    for _ in range(20):
        code = "YTK-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
        if session.exec(select(Transaction).where(Transaction.authorization_code == code)).first() is None:
            return code
    raise RuntimeError("authorization code collision budget exhausted")


def _latency(started: float) -> int:
    return max(1, int((time.perf_counter() - started) * 1000))


def _audit(
    session: Session,
    transaction: Transaction,
    correlation_id: str,
    outcome: str,
    *,
    actor: str | None = None,
) -> None:
    audit_service.record(
        session,
        actor=actor or transaction.initiator,
        action=AuditAction.TRANSACTION_COSIGNED if actor else AuditAction.TRANSACTION_AUTHORIZED,
        entity_type=AuditEntity.TRANSACTION,
        entity_id=transaction.id,
        correlation_id=correlation_id,
        detail={
            "outcome": outcome,
            "verdict": transaction.verdict.value if transaction.verdict else None,
            "amount_minor": transaction.amount_minor,
            "currency": transaction.currency,
            "subject": transaction.subject.value,
        },
    )


def _audit_rejected_cosign(
    session: Session,
    transaction: Transaction,
    cosigner: str,
    correlation_id: str,
    outcome: str,
) -> None:
    _audit(session, transaction, correlation_id, outcome, actor=cosigner)
    session.commit()


def _cosign_error(message: str) -> ApiError:
    return ApiError(ErrorCode.COSIGN_NOT_ALLOWED, message, status_code=409)
