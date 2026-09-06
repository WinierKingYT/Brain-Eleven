"""Scoped idempotency identity; receipts live inside the canonical stores."""
from contextlib import contextmanager
from contextvars import ContextVar
import re

operation_id = ContextVar("brain_eleven_operation_id", default=None)
operation_request = ContextVar("brain_eleven_operation_request", default=None)
operation_result = ContextVar("brain_eleven_operation_result", default=None)


@contextmanager
def operation(identity, request_hash=None):
    if not isinstance(identity, str) or not re.fullmatch(r"op_[a-f0-9]{64}", identity):
        raise ValueError("Invalid operation identity")
    token = operation_id.set(identity)
    request_token = operation_request.set(request_hash)
    result_token = operation_result.set(None)
    try:
        yield
    finally:
        operation_id.reset(token)
        operation_request.reset(request_token)
        operation_result.reset(result_token)


def validate_receipts(value):
    if not isinstance(value, dict):
        raise ValueError("Operation receipts must be an object")
    for key, receipt in value.items():
        if not re.fullmatch(r"op_[a-f0-9]{64}", key) or not isinstance(receipt, dict):
            raise ValueError("Invalid operation receipt")
    return value
