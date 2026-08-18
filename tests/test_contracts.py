"""Unit tests for the falsification report contract."""

from __future__ import annotations

from falsification_ledger.contracts import (
    evidence_status,
    falsification_object_id,
    validate_falsification_report,
)


def _valid_report(**overrides) -> dict:
    report = {
        "schema_version": "falsification_ledger.falsification_report.v1",
        "candidate_artifact_id": "sha256:" + "a" * 64,
        "candidate_type": "factor",
        "falsification_type": "null_model_randomization",
        "null_model": {
            "construction": "permute labels",
            "n_permutations": 1000,
            "distribution": "permutation",
            "random_seed": 42,
            "seed_fixed": True,
        },
        "metrics": [
            {
                "name": "rank_ic",
                "value": 0.03,
                "p_value": 0.04,
                "null_distribution": {"n_permutations": 1000, "seed": 42, "reproducible": True},
            }
        ],
        "conclusion": "not_falsified",
        "program": {"name": "null-check", "version": "1.0.0"},
        "data_window": {"start": "2020-01-01", "end": "2026-01-01"},
        "generated_at": "2026-08-18T12:00:00+08:00",
        "safety_contract": {
            "production_effect": False,
            "changes_probability": False,
            "allow_real_trade": False,
        },
    }
    report.update(overrides)
    return report


def test_valid_report_passes() -> None:
    assert validate_falsification_report(_valid_report()) == []


def test_missing_required_field_blocked() -> None:
    report = _valid_report()
    del report["null_model"]
    blockers = validate_falsification_report(report)
    assert any("null_model" in blocker for blocker in blockers)


def test_wrong_schema_version_blocked() -> None:
    report = _valid_report(schema_version="someone_else.v1")
    blockers = validate_falsification_report(report)
    assert any("schema_version" in blocker for blocker in blockers)


def test_wrong_consistency_tolerance_blocked() -> None:
    report = _valid_report(
        consistency={
            "compared_report_id": "sha256:" + "b" * 64,
            "max_p_value_diff": 0.001,
            "tolerance": 0.01,
            "consistent": True,
        }
    )
    blockers = validate_falsification_report(report)
    assert any("tolerance" in blocker for blocker in blockers)


def test_falsified_conclusion_is_invalid_evidence() -> None:
    report = _valid_report(conclusion="falsified")
    assert evidence_status(report) == "invalid"


def test_inconclusive_is_missing_evidence() -> None:
    report = _valid_report(conclusion="inconclusive")
    assert evidence_status(report) == "missing"


def test_not_falsified_is_valid_evidence() -> None:
    report = _valid_report(conclusion="not_falsified")
    assert evidence_status(report) == "valid"


def test_inconsistent_report_is_invalid() -> None:
    report = _valid_report(
        consistency={
            "compared_report_id": "sha256:" + "c" * 64,
            "max_p_value_diff": 0.001,
            "tolerance": 0.005,
            "consistent": False,
        }
    )
    assert evidence_status(report) == "invalid"


def test_content_id_is_stable_and_content_addressed() -> None:
    first = _valid_report()
    second = _valid_report()
    assert falsification_object_id(first) == falsification_object_id(second)
    changed = _valid_report(note="one different field")
    assert falsification_object_id(changed) != falsification_object_id(first)
    assert falsification_object_id(first).startswith("sha256:")
