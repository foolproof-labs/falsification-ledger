"""Unit tests for the hash-chained prediction ledger."""

from __future__ import annotations

import json

import pytest

from falsification_ledger.ledger import (
    conclude_prediction,
    ensure_prediction_registered,
    has_prediction_registered,
    ledger_path,
    register_prediction,
    report_prediction_hitrate,
    verify_chain,
)


@pytest.fixture()
def state(tmp_path):
    return str(tmp_path / "ledger")


def test_register_and_chain(state) -> None:
    register_prediction(state, "CASE-1", "support", "momentum persists OOS")
    events = [json.loads(line) for line in ledger_path(state).read_text(encoding="utf-8").splitlines()]
    assert len(events) == 1
    assert events[0]["event"] == "register"
    assert events[0]["prev_hash"] is None
    assert events[0]["event_hash"]
    body = verify_chain(state)
    assert body["ok"] is True
    assert body["events"] == 1


def test_register_rejects_duplicate(state) -> None:
    register_prediction(state, "CASE-1", "support", "reason")
    with pytest.raises(ValueError, match="duplicate_register"):
        register_prediction(state, "CASE-1", "against", "reason")


def test_register_rejects_bad_verdict(state) -> None:
    with pytest.raises(ValueError, match="invalid_verdict"):
        register_prediction(state, "CASE-1", "maybe", "reason")


def test_register_requires_reason(state) -> None:
    with pytest.raises(ValueError, match="expected_reason_required"):
        register_prediction(state, "CASE-1", "support", "   ")


def test_ensure_idempotent(state) -> None:
    first = ensure_prediction_registered(state, "CASE-1", "support", "reason")
    assert first["already_registered"] is False
    second = ensure_prediction_registered(state, "CASE-1", "support", "reason")
    assert second["already_registered"] is True


def test_conclude_requires_register(state) -> None:
    with pytest.raises(ValueError, match="register_required"):
        conclude_prediction(state, "CASE-1", "support")


def test_conclude_once_only(state) -> None:
    register_prediction(state, "CASE-1", "support", "reason")
    conclude_prediction(state, "CASE-1", "support")
    with pytest.raises(ValueError, match="already_concluded"):
        conclude_prediction(state, "CASE-1", "against")


def test_verify_detects_tampering(state) -> None:
    register_prediction(state, "CASE-1", "support", "reason")
    register_prediction(state, "CASE-2", "against", "reason")
    path = ledger_path(state)
    lines = path.read_text(encoding="utf-8").splitlines()
    # tamper with the first event's reason without touching hashes
    tampered = json.loads(lines[0])
    tampered["expected_reason"] = "rewritten after the fact"
    lines[0] = json.dumps(tampered)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    body = verify_chain(state)
    assert body["ok"] is False
    assert body["first_bad_line"] == 1


def test_verify_detects_chain_break_on_append_edit(state) -> None:
    register_prediction(state, "CASE-1", "support", "reason")
    path = ledger_path(state)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0][:-1] + "0"  # corrupt the event_hash hex
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert verify_chain(state)["ok"] is False


def test_report_hitrate_with_baseline(state) -> None:
    # 3 certain hits out of 5; actual distribution favors "against".
    for case, expected in [("A", "support"), ("B", "against"), ("C", "against"), ("D", "uncertain")]:
        register_prediction(state, case, expected, "reason")
    conclude_prediction(state, "A", "support")   # hit
    conclude_prediction(state, "B", "against")   # hit
    conclude_prediction(state, "C", "support")   # miss
    conclude_prediction(state, "D", "against")   # uncertain: participation only
    report = report_prediction_hitrate(state)
    assert report["resolved_cases"] == 4
    assert report["certain_cases"] == 3
    assert report["uncertain_cases"] == 1
    assert report["hit_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert report["random_baseline"] == pytest.approx(2 / 3, abs=1e-4)
    assert report["verdict_ready"] is False  # 4 < 20 min cases


def test_report_ready_when_thresholds_met(state) -> None:
    # 20 resolved cases; 16 hits. Actual distribution favors "support"
    # (16 vs 4), so the random baseline is 0.8 — identical to the hit rate,
    # which the Wilson CI contains: no systematic signal, verdict still ready.
    for case, expected in [(f"C{i:02d}", "support") for i in range(20)]:
        register_prediction(state, case, expected, "reason")
    for i, case in enumerate([f"C{i:02d}" for i in range(20)]):
        conclude_prediction(state, case, "support" if i < 16 else "against")
    report = report_prediction_hitrate(state, min_cases=20)
    assert report["verdict_ready"] is True
    assert report["hit_rate"] == pytest.approx(0.8, abs=1e-4)
    assert report["random_baseline"] == pytest.approx(0.8, abs=1e-4)
    assert report["baseline_in_ci"] is True
