"""End-to-end CLI tests: preregister -> adjudicate -> report -> verify."""

from __future__ import annotations

import json

import pytest

from falsification_ledger.cli import main
from falsification_ledger.ledger import ledger_path

SCHEMA_DIR = __import__("pathlib").Path(__file__).resolve().parents[1] / "schema"


@pytest.fixture()
def state(tmp_path):
    return str(tmp_path / "ledger")


def test_cli_version() -> None:
    assert main(["version"]) == 0


def test_cli_preregister_adjudicate_report_verify(state, capsys) -> None:
    assert main(["init", "--state-dir", state]) == 0
    assert main(
        [
            "preregister",
            "--state-dir", state,
            "--case-id", "CASE-1",
            "--verdict", "support",
            "--reason", "momentum persists OOS",
        ]
    ) == 0
    assert main(
        [
            "adjudicate",
            "--state-dir", state,
            "--case-id", "CASE-1",
            "--verdict", "support",
        ]
    ) == 0
    capsys.readouterr()  # discard earlier command output
    assert main(["report", "--state-dir", state, "--min-cases", "1"]) == 0
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["resolved_cases"] == 1
    assert report["hit_rate"] == 1.0
    assert main(["verify", "--state-dir", state]) == 0


def test_cli_preregister_with_contract(state, tmp_path) -> None:
    contract = {"evidence_that_kills": "oos rank ic p-value > 0.1"}
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    assert (
        main(
            [
                "preregister",
                "--state-dir", state,
                "--case-id", "CASE-2",
                "--verdict", "against",
                "--reason", "reversal fades",
                "--contract", str(contract_path),
            ]
        )
        == 0
    )
    events = [json.loads(line) for line in ledger_path(state).read_text(encoding="utf-8").splitlines()]
    assert events[0]["falsification_contract"] == contract


def test_cli_submit_valid_report(tmp_path, capsys) -> None:
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
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    assert main(["submit", "--report", str(report_path)]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["evidence_status"] == "valid"
    assert body["content_id"].startswith("sha256:")


def test_cli_submit_invalid_report_fails(tmp_path, capsys) -> None:
    report_path = tmp_path / "bad.json"
    report_path.write_text(json.dumps({"schema_version": "wrong"}), encoding="utf-8")
    assert main(["submit", "--report", str(report_path)]) == 1


def test_cli_verify_detects_tamper(state) -> None:
    main(["init", "--state-dir", state])
    main(
        [
            "preregister",
            "--state-dir", state,
            "--case-id", "CASE-1",
            "--verdict", "support",
            "--reason", "reason",
        ]
    )
    path = ledger_path(state)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = lines[0][:-1] + "0"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert main(["verify", "--state-dir", state]) == 1
