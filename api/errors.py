"""Application errors and the standard error envelope — plan section 5.7.

Every non-2xx response is::

    {"error": {"code", "message", "retryable", "details", "correlation_id"}}

`message` is user-facing Turkish. Section 5.7 and section 14: never return a
stack trace, a raw model response, a local path or a secret. `ApiError` carries
only what is safe to show, so an unexpected exception can be turned into a
generic `INTERNAL_ERROR` without leaking the original.
"""

from __future__ import annotations

from typing import Any

from api.schemas import ErrorCode


class ApiError(Exception):
    """An error with a defined contract code, HTTP status and Turkish message."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int = 400,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}

    def to_body(self, correlation_id: str) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code.value,
                "message": self.message,
                "retryable": self.retryable,
                "details": self.details,
                "correlation_id": correlation_id,
            }
        }


def not_found(entity: str, entity_id: object) -> ApiError:
    return ApiError(
        ErrorCode.NOT_FOUND,
        f"{entity} bulunamadı.",
        status_code=404,
        details={"entity": entity, "id": str(entity_id)},
    )


def invalid_state_transition(current: str, target: str) -> ApiError:
    """Plan section 7.2: invalid transitions return 409."""
    return ApiError(
        ErrorCode.INVALID_STATE_TRANSITION,
        f"Bu işlem şu anki durumda yapılamaz ({current} → {target}).",
        status_code=409,
        details={"from": current, "to": target},
    )


def demo_mode_disabled() -> ApiError:
    """Plan section 14: demo mutation endpoints require DEMO_MODE=true."""
    return ApiError(
        ErrorCode.DEMO_MODE_DISABLED,
        "Demo modu kapalı olduğu için bu işlem kullanılamaz.",
        status_code=403,
    )


def unknown_case(case_number: object) -> ApiError:
    return ApiError(
        ErrorCode.UNKNOWN_CASE,
        f"{case_number} numaralı demo senaryosu tanımlı değil.",
        status_code=404,
        details={"case": str(case_number)},
    )


def registry_unavailable() -> ApiError:
    """Plan section 15: a registry read failure fails closed."""
    return ApiError(
        ErrorCode.REGISTRY_UNAVAILABLE,
        "Sicil kaydı okunamadı. Güvenlik gereği işlem durduruldu.",
        status_code=503,
        retryable=True,
    )
