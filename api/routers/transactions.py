"""Mobile authorization, co-sign and history endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from api.db import get_session
from api.schemas import AuthorizeTransactionRequest, CosignTransactionRequest, TransactionDecision
from api.services import transaction_service

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.post("/authorize", response_model=TransactionDecision)
def authorize_transaction(
    payload: AuthorizeTransactionRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> TransactionDecision:
    return transaction_service.authorize(
        session, payload, correlation_id=request.state.correlation_id
    )


@router.post("/{transaction_id}/cosign", response_model=TransactionDecision)
def cosign_transaction(
    transaction_id: int,
    payload: CosignTransactionRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> TransactionDecision:
    return transaction_service.cosign(
        session, transaction_id, payload, correlation_id=request.state.correlation_id
    )


@router.get("", response_model=list[TransactionDecision])
def transaction_history(
    mersis: str, session: Annotated[Session, Depends(get_session)]
) -> list[TransactionDecision]:
    return transaction_service.history(session, mersis)
