"""Binding store: AccountId <-> AttemptId <-> SessionId with a state machine.

Prevents session hijacking/replay by persisting the binding created when a
liveness session is issued, and re-validating it before returning results.

State machine (AttemptId lifecycle):
    CREATED  -> STARTED -> COMPLETED
       |           |
       +-----------+--> FAILED / EXPIRED

- CREATED:   session issued & bound; awaiting the client to run the check.
- STARTED:   client signalled analysis complete (optional transition).
- COMPLETED: GetFaceLivenessSessionResults consumed once (terminal, no replay).
- FAILED:    result retrieval failed / liveness not passed (terminal).
- EXPIRED:   TTL passed before completion (terminal).

The default store is in-memory (single-process demo). A DynamoDB-backed store
can implement the same interface for production (with TTL attribute). See
`InMemoryBindingStore` docstring for the DynamoDB mapping.
"""
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class AttemptState(str, Enum):
    CREATED = "CREATED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


# Allowed transitions.
_ALLOWED = {
    AttemptState.CREATED: {AttemptState.STARTED, AttemptState.COMPLETED,
                           AttemptState.FAILED, AttemptState.EXPIRED},
    AttemptState.STARTED: {AttemptState.COMPLETED, AttemptState.FAILED,
                           AttemptState.EXPIRED},
    AttemptState.COMPLETED: set(),
    AttemptState.FAILED: set(),
    AttemptState.EXPIRED: set(),
}

# SessionId is valid for 3 minutes per AWS; expire the binding accordingly.
DEFAULT_TTL_SECONDS = 180


class BindingError(Exception):
    """Raised for binding validation / state-machine violations."""


@dataclass
class Binding:
    attempt_id: str
    account_id: str
    session_id: str
    state: AttemptState = AttemptState.CREATED
    created_at: float = field(default_factory=time.time)
    ttl_seconds: int = DEFAULT_TTL_SECONDS

    def is_expired(self, now: Optional[float] = None) -> bool:
        now = now if now is not None else time.time()
        return (now - self.created_at) > self.ttl_seconds


class InMemoryBindingStore:
    """Thread-safe in-memory binding store.

    DynamoDB production mapping (same interface):
      Table PK = attempt_id
      Attributes: account_id, session_id, state, created_at
      TTL attribute = created_at + ttl_seconds (enable DynamoDB TTL)
      Use a conditional update on `state` to enforce transitions atomically.
    """

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self._d: Dict[str, Binding] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def create(self, account_id: str, session_id: str) -> Binding:
        attempt_id = f"att-{uuid.uuid4().hex}"
        b = Binding(attempt_id=attempt_id, account_id=account_id,
                    session_id=session_id, ttl_seconds=self._ttl)
        with self._lock:
            self._d[attempt_id] = b
        return b

    def get(self, attempt_id: str) -> Optional[Binding]:
        with self._lock:
            return self._d.get(attempt_id)

    def validate(self, attempt_id: str, account_id: str, session_id: str) -> Binding:
        """Re-validate the full triple binding. Raises BindingError on mismatch,
        expiry, or terminal state."""
        with self._lock:
            b = self._d.get(attempt_id)
            if b is None:
                raise BindingError("Unknown attemptId.")
            if b.account_id != account_id:
                raise BindingError("AccountId does not match binding.")
            if b.session_id != session_id:
                raise BindingError("SessionId does not match binding.")
            if b.state in (AttemptState.COMPLETED, AttemptState.FAILED):
                raise BindingError(f"Attempt already terminal ({b.state}). Replay denied.")
            if b.is_expired():
                b.state = AttemptState.EXPIRED
                raise BindingError("Attempt expired (session valid for 3 minutes).")
            return b

    def transition(self, attempt_id: str, new_state: AttemptState) -> Binding:
        with self._lock:
            b = self._d.get(attempt_id)
            if b is None:
                raise BindingError("Unknown attemptId.")
            if new_state not in _ALLOWED[b.state]:
                raise BindingError(f"Illegal transition {b.state} -> {new_state}.")
            b.state = new_state
            return b


# Module-level default store (swap for DynamoDB store via set_store()).
_store: InMemoryBindingStore = InMemoryBindingStore()


def get_store() -> InMemoryBindingStore:
    return _store


def set_store(store: InMemoryBindingStore) -> None:
    global _store
    _store = store
