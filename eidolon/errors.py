"""Typed library exceptions for the Eidolon Engine.

Library functions raise these instead of encoding HTTP status codes into
``ValueError`` message prefixes (the old ``"404:message"`` convention). The
``authenticated_handler`` decorator maps each exception type to its HTTP status
code in one place, keeping HTTP concerns out of the library.

Each exception carries a ``status_code`` class attribute and the message passed
to it, so a handler can respond with ``(err.status_code, str(err))``.
"""


class EidolonError(Exception):
    """Base class for library errors that map to an HTTP status code."""

    status_code = 500

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ValidationError(EidolonError):
    """Invalid input or request the caller can correct. Maps to 400."""

    status_code = 400


class UnauthorizedError(EidolonError):
    """Caller is not authenticated or the player record is missing. Maps to 401."""

    status_code = 401


class PaymentRequiredError(EidolonError):
    """Caller cannot afford the requested action. Maps to 402."""

    status_code = 402


class AccessDeniedError(EidolonError):
    """Caller is authenticated but does not own the target resource. Maps to 403."""

    status_code = 403


class NotFoundError(EidolonError):
    """Requested resource does not exist or is not visible to the caller. Maps to 404."""

    status_code = 404


class ConflictError(EidolonError):
    """Request conflicts with current state (race, duplicate, wrong mode). Maps to 409."""

    status_code = 409
