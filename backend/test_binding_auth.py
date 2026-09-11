"""Automated tests for token auth + session binding + AttemptId state machine.

Rekognition service calls are monkeypatched so tests run offline (no AWS).
Run:  pytest -q   (from the backend/ directory)
"""
import time

import pytest
from fastapi.testclient import TestClient

import main
import rekognition_service as svc
from binding_store import (
    AttemptState,
    BindingError,
    InMemoryBindingStore,
    set_store,
    get_store,
)

ALICE = {"Authorization": "Bearer demo-token-alice"}
BOB = {"Authorization": "Bearer demo-token-bob"}


@pytest.fixture(autouse=True)
def fresh_store():
    # Isolate each test with a fresh binding store.
    set_store(InMemoryBindingStore())
    yield


@pytest.fixture
def client(monkeypatch):
    # Stub AWS calls.
    monkeypatch.setattr(svc, "create_liveness_session", lambda: "sess-FAKE-123")

    def fake_verify_and_enroll(session_id):
        return {
            "isLive": True,
            "livenessConfidence": 97.5,
            "duplicate": False,
            "matches": [],
            "enrolledUserId": "user-fake",
            "enrolledFaceId": "face-fake",
            "message": "ok",
        }

    monkeypatch.setattr(svc, "liveness_verify_and_enroll", fake_verify_and_enroll)
    return TestClient(main.app)


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
def test_create_session_requires_token(client):
    r = client.post("/api/secure/liveness/session")
    assert r.status_code == 401


def test_create_session_rejects_bad_token(client):
    r = client.post("/api/secure/liveness/session",
                    headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_create_session_ok_with_valid_token(client):
    r = client.post("/api/secure/liveness/session", headers=ALICE)
    assert r.status_code == 200
    body = r.json()
    assert body["sessionId"] == "sess-FAKE-123"
    assert body["accountId"] == "acct-alice-001"
    assert body["attemptId"].startswith("att-")
    assert body["state"] == "CREATED"


# --------------------------------------------------------------------------
# Binding validation on complete
# --------------------------------------------------------------------------
def _create(client, headers=ALICE):
    r = client.post("/api/secure/liveness/session", headers=headers)
    return r.json()


def test_complete_happy_path(client):
    b = _create(client)
    r = client.post(
        f"/api/secure/liveness/attempt/{b['attemptId']}/complete",
        headers=ALICE, data={"session_id": b["sessionId"]},
    )
    assert r.status_code == 200
    assert r.json()["isLive"] is True
    # Attempt is now terminal COMPLETED.
    assert get_store().get(b["attemptId"]).state == AttemptState.COMPLETED


def test_complete_wrong_account_denied(client):
    b = _create(client, headers=ALICE)
    # Bob tries to complete Alice's attempt.
    r = client.post(
        f"/api/secure/liveness/attempt/{b['attemptId']}/complete",
        headers=BOB, data={"session_id": b["sessionId"]},
    )
    assert r.status_code == 403
    assert "AccountId" in r.json()["detail"]


def test_complete_wrong_session_denied(client):
    b = _create(client)
    r = client.post(
        f"/api/secure/liveness/attempt/{b['attemptId']}/complete",
        headers=ALICE, data={"session_id": "sess-OTHER"},
    )
    assert r.status_code == 403
    assert "SessionId" in r.json()["detail"]


def test_complete_unknown_attempt_denied(client):
    b = _create(client)
    r = client.post(
        "/api/secure/liveness/attempt/att-doesnotexist/complete",
        headers=ALICE, data={"session_id": b["sessionId"]},
    )
    assert r.status_code == 403
    assert "Unknown attemptId" in r.json()["detail"]


def test_replay_denied(client):
    b = _create(client)
    ok = client.post(
        f"/api/secure/liveness/attempt/{b['attemptId']}/complete",
        headers=ALICE, data={"session_id": b["sessionId"]},
    )
    assert ok.status_code == 200
    # Second attempt (replay) must be denied — attempt is terminal.
    replay = client.post(
        f"/api/secure/liveness/attempt/{b['attemptId']}/complete",
        headers=ALICE, data={"session_id": b["sessionId"]},
    )
    assert replay.status_code == 403
    assert "terminal" in replay.json()["detail"].lower()


# --------------------------------------------------------------------------
# State machine + expiry (unit level)
# --------------------------------------------------------------------------
def test_state_machine_illegal_transition():
    store = InMemoryBindingStore()
    b = store.create("acct-x", "sess-x")
    store.transition(b.attempt_id, AttemptState.COMPLETED)
    with pytest.raises(BindingError):
        store.transition(b.attempt_id, AttemptState.STARTED)


def test_binding_expiry():
    store = InMemoryBindingStore(ttl_seconds=0)  # immediate expiry
    b = store.create("acct-x", "sess-x")
    time.sleep(0.01)
    with pytest.raises(BindingError) as ei:
        store.validate(b.attempt_id, "acct-x", "sess-x")
    assert "expired" in str(ei.value).lower()
    assert store.get(b.attempt_id).state == AttemptState.EXPIRED


def test_valid_transitions():
    store = InMemoryBindingStore()
    b = store.create("acct-x", "sess-x")
    assert b.state == AttemptState.CREATED
    store.transition(b.attempt_id, AttemptState.STARTED)
    assert store.get(b.attempt_id).state == AttemptState.STARTED
    store.transition(b.attempt_id, AttemptState.COMPLETED)
    assert store.get(b.attempt_id).state == AttemptState.COMPLETED
