"""Append-only, hash-chained prediction ledger core.

The ledger answers one question honestly: *did your pre-registered beliefs
hit?*  Events are appended to a JSONL file; every event carries the hash of
the previous event, so the file is a hash chain and any edit is detectable
by ``verify_chain``.

Event kinds:

- ``register``   — a claim about a case: expected verdict + reason, recorded
  before evidence is seen (one per case, duplicate rejected).
- ``conclude``   — the actual verdict, backfilled at study end (requires a
  prior register; once per case).

Reports aggregate resolved cases into a hit rate with a Wilson 95% CI and
compare it against the random baseline (most common actual verdict): if the
baseline is inside the CI, there is no systematic signal.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import uuid
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "falsification_ledger.prediction_event.v1"
REPORT_SCHEMA_VERSION = "falsification_ledger.prediction_report.v1"
VERDICTS = ("support", "against", "uncertain")
SOURCE_TYPES = ("paper", "business", "cross_domain", "pipeline", "other")
DEFAULT_MIN_CASES = 20
SAFETY = {
    "production_effect": False,
    "changes_probability": False,
    "allow_real_trade": False,
}


def _now_text() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _event_hash(prev_hash: str | None, payload: dict[str, Any]) -> str:
    """sha256(prev_hash || 0x00 || canonical payload)."""
    body = (prev_hash or "").encode("utf-8") + b"\x00" + _canonical_bytes(payload)
    return hashlib.sha256(body).hexdigest()


def ledger_path(state_dir: Path | str) -> Path:
    return Path(state_dir) / "ledger.jsonl"


def _load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line_no, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"ledger_corrupt:{path}:{line_no}") from exc
    return events


def _append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _last_hash(events: list[dict[str, Any]]) -> str | None:
    return events[-1].get("event_hash") if events else None


def register_prediction(
    state_dir: Path | str,
    case_id: str,
    expected_verdict: str,
    expected_reason: str,
    source_type: str = "other",
    *,
    falsification_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Register a claim about a case (once per case; duplicates rejected).

    ``falsification_contract`` is optional free-form JSON describing what
    evidence would kill the claim — written down *before* the study runs.
    """
    if expected_verdict not in VERDICTS:
        raise ValueError(f"invalid_verdict:{expected_verdict}")
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"invalid_source_type:{source_type}")
    if not expected_reason.strip():
        raise ValueError("expected_reason_required")
    path = ledger_path(state_dir)
    events = _load_events(path)
    if any(
        e.get("case_id") == case_id and e.get("event") == "register"
        for e in events
    ):
        raise ValueError(f"duplicate_register:{case_id}")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "event": "register",
        "record_id": str(uuid.uuid4()),
        "case_id": case_id,
        "expected_verdict": expected_verdict,
        "expected_reason": expected_reason.strip(),
        "source_type": source_type,
        "falsification_contract": falsification_contract,
        "actual_verdict": None,
        "recorded_at": _now_text(),
        "concluded_at": None,
    }
    event = {**payload, "prev_hash": _last_hash(events)}
    event["event_hash"] = _event_hash(event["prev_hash"], payload)
    _append_event(path, event)
    return {"event": "register", "case_id": case_id, "recorded_at": event["recorded_at"]}


def has_prediction_registered(state_dir: Path | str, case_id: str) -> bool:
    """Whether the case already has a registration (required before conclude)."""
    path = ledger_path(state_dir)
    return any(
        e.get("case_id") == case_id and e.get("event") == "register"
        for e in _load_events(path)
    )


def ensure_prediction_registered(
    state_dir: Path | str,
    case_id: str,
    expected_verdict: str,
    expected_reason: str,
    source_type: str = "other",
) -> dict[str, Any]:
    """Idempotent register: skip when already registered (for automation)."""
    if has_prediction_registered(state_dir, case_id):
        return {"event": "register", "case_id": case_id, "already_registered": True}
    return {
        **register_prediction(
            state_dir, case_id, expected_verdict, expected_reason, source_type
        ),
        "already_registered": False,
    }


def conclude_prediction(
    state_dir: Path | str,
    case_id: str,
    actual_verdict: str,
) -> dict[str, Any]:
    """Backfill the actual verdict (register required; once per case)."""
    if actual_verdict not in VERDICTS:
        raise ValueError(f"invalid_verdict:{actual_verdict}")
    path = ledger_path(state_dir)
    events = _load_events(path)
    if not any(
        e.get("case_id") == case_id and e.get("event") == "register"
        for e in events
    ):
        raise ValueError(f"register_required:{case_id}")
    if any(
        e.get("case_id") == case_id and e.get("event") == "conclude"
        for e in events
    ):
        raise ValueError(f"already_concluded:{case_id}")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "event": "conclude",
        "record_id": str(uuid.uuid4()),
        "case_id": case_id,
        "actual_verdict": actual_verdict,
        "recorded_at": _now_text(),
        "concluded_at": _now_text(),
    }
    event = {**payload, "prev_hash": _last_hash(events)}
    event["event_hash"] = _event_hash(event["prev_hash"], payload)
    _append_event(path, event)
    return {"event": "conclude", "case_id": case_id, "concluded_at": event["concluded_at"]}


def verify_chain(state_dir: Path | str) -> dict[str, Any]:
    """Recompute and check the hash chain of the whole ledger.

    Detects any edit, insertion, or reordering after the fact.  Read-only.
    """
    path = ledger_path(state_dir)
    if not path.exists():
        return {"exists": False, "ok": True, "events": 0, "first_bad_line": None}
    problems: list[dict[str, Any]] = []
    prev_hash: str | None = None
    events = 0
    for line_no, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            problems.append({"line": line_no, "reason": f"invalid_json:{exc.msg}"})
            continue
        if not isinstance(event, dict):
            problems.append({"line": line_no, "reason": "not_object"})
            continue
        events += 1
        stored_prev = event.get("prev_hash") or None
        if stored_prev != prev_hash:
            problems.append(
                {
                    "line": line_no,
                    "reason": "prev_hash_mismatch",
                    "expected": prev_hash,
                    "found": stored_prev,
                }
            )
        payload = {
            key: value
            for key, value in event.items()
            if key not in ("event_hash", "prev_hash")
        }
        expected = _event_hash(stored_prev, payload)
        if event.get("event_hash") != expected:
            problems.append(
                {"line": line_no, "reason": "event_hash_mismatch", "expected": expected}
            )
        prev_hash = event.get("event_hash")
    return {
        "exists": True,
        "ok": not problems,
        "events": events,
        "first_bad_line": problems[0]["line"] if problems else None,
        "problems": problems[:20],
    }


def _wilson_ci(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = hits / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def report_prediction_hitrate(
    state_dir: Path | str,
    min_cases: int = DEFAULT_MIN_CASES,
) -> dict[str, Any]:
    """Read-only hit-rate report (Wilson 95% CI, compared against random baseline).

    Rule: a hit is ``expected_verdict == actual_verdict`` over *certain*
    expectations; ``uncertain`` expectations count into participation only.
    The report is verdict-ready when ``resolved >= min_cases``,
    ``completeness >= 0.9`` and ``participation >= 0.7``.  If the Wilson CI
    contains the random baseline, there is no systematic signal.
    """
    events = _load_events(ledger_path(state_dir))
    registers = {
        e["case_id"]: e for e in events if e.get("event") == "register"
    }
    concludes = {
        e["case_id"]: e for e in events if e.get("event") == "conclude"
    }
    resolved = sorted(set(registers) & set(concludes))
    unresolved = sorted(set(registers) - set(concludes))
    registered_total = len(registers)
    completeness = (
        len(resolved) / registered_total if registered_total else 0.0
    )
    hits = 0
    certain_cases = 0
    uncertain_cases = 0
    for case in resolved:
        expected = registers[case]["expected_verdict"]
        if expected == "uncertain":
            uncertain_cases += 1
            continue
        certain_cases += 1
        if expected == concludes[case]["actual_verdict"]:
            hits += 1
    n = len(resolved)
    hit_rate = hits / certain_cases if certain_cases else None
    low, high = _wilson_ci(hits, certain_cases) if certain_cases else (None, None)
    participation = certain_cases / n if n else 0.0
    actual_distribution: dict[str, int] = {}
    for case in resolved:
        if registers[case]["expected_verdict"] == "uncertain":
            continue
        verdict = concludes[case]["actual_verdict"]
        actual_distribution[verdict] = actual_distribution.get(verdict, 0) + 1
    baseline = (
        max(actual_distribution.values()) / certain_cases if certain_cases else None
    )
    baseline_in_ci = (
        low <= baseline <= high if (low is not None and baseline is not None) else None
    )
    by_source_type: dict[str, dict[str, Any]] = {}
    for case in resolved:
        source = registers[case].get("source_type", "other")
        bucket = by_source_type.setdefault(
            source, {"resolved": 0, "certain": 0, "hits": 0, "hit_rate": None}
        )
        bucket["resolved"] += 1
        expected = registers[case]["expected_verdict"]
        if expected == "uncertain":
            continue
        bucket["certain"] += 1
        if expected == concludes[case]["actual_verdict"]:
            bucket["hits"] += 1
    for source, bucket in by_source_type.items():
        bucket["hit_rate"] = (
            bucket["hits"] / bucket["certain"] if bucket["certain"] else None
        )
    verdict_ready = (
        n >= min_cases and completeness >= 0.9 and participation >= 0.7
    )
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": _now_text(),
        "min_cases": min_cases,
        "resolved_cases": n,
        "unresolved_cases": len(unresolved),
        "registered_total": registered_total,
        "completeness": round(completeness, 4),
        "certain_cases": certain_cases,
        "uncertain_cases": uncertain_cases,
        "participation": round(participation, 4),
        "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
        "wilson_ci_95": [round(low, 4), round(high, 4)]
        if low is not None
        else None,
        "random_baseline": round(baseline, 4) if baseline is not None else None,
        "baseline_in_ci": baseline_in_ci,
        "actual_verdict_distribution": actual_distribution,
        "by_source_type": by_source_type,
        "verdict_ready": verdict_ready,
        "verdict_rule": (
            "hit = expected_verdict == actual_verdict, only over certain "
            "expectations; uncertain expectations count into participation; "
            "ready when resolved>=min_cases and completeness>=0.9 and "
            "participation>=0.7; "
            "if wilson_ci_95 contains random_baseline -> no systematic signal"
        ),
        "safety": SAFETY,
    }
