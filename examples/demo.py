"""End-to-end demo: preregister -> submit evidence -> adjudicate -> report -> verify.

Run with:  python examples/demo.py
Writes a scratch ledger under a temporary directory; safe to re-run.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from falsification_ledger.cli import main as cli_main  # noqa: E402
from falsification_ledger.ledger import ledger_path  # noqa: E402

STATE_DIR = Path(tempfile.mkdtemp(prefix="fl-demo-"))
SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schema"


def _run(label: str, argv: list[str]) -> int:
    print(f"\n== {label} ==")
    return cli_main(argv)


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    _run("0. init", ["init", "--state-dir", str(STATE_DIR)])

    contract = {
        "kills_when": "oos rank IC p-value > 0.10 with n>=300 bars",
        "power_target": 0.8,
        "preregistered_before_evidence": True,
    }
    contract_path = STATE_DIR / "contract.json"
    _write(contract_path, contract)

    _run(
        "1. preregister (expectation + falsification contract, BEFORE evidence)",
        [
            "preregister",
            "--state-dir", str(STATE_DIR),
            "--case-id", "MOMENTUM-OOS-2026Q3",
            "--verdict", "support",
            "--reason", "momentum rank IC stays positive out-of-sample",
            "--source-type", "paper",
            "--contract", str(contract_path),
        ],
    )

    report = {
        "schema_version": "falsification_ledger.falsification_report.v1",
        "candidate_artifact_id": "sha256:" + "a" * 64,
        "candidate_type": "factor",
        "falsification_type": "null_model_randomization",
        "null_model": {
            "construction": "permute labels within session",
            "n_permutations": 1000,
            "distribution": "permutation",
            "random_seed": 42,
            "seed_fixed": True,
        },
        "metrics": [
            {
                "name": "oos_rank_ic",
                "value": 0.031,
                "p_value": 0.04,
                "null_distribution": {"n_permutations": 1000, "seed": 42, "reproducible": True},
            }
        ],
        "conclusion": "not_falsified",
        "program": {"name": "oos-null-check", "version": "1.0.0"},
        "data_window": {"start": "2025-01-01", "end": "2026-08-01"},
        "generated_at": "2026-08-18T12:00:00+08:00",
        "safety_contract": {
            "production_effect": False,
            "changes_probability": False,
            "allow_real_trade": False,
        },
    }
    report_path = STATE_DIR / "report.json"
    _write(report_path, report)

    _run("2. submit evidence (content ID + fail-closed evidence status)", ["submit", "--report", str(report_path)])

    _run(
        "3. adjudicate honestly (AFTER the study)",
        [
            "adjudicate",
            "--state-dir", str(STATE_DIR),
            "--case-id", "MOMENTUM-OOS-2026Q3",
            "--verdict", "support",
        ],
    )

    _run("4. report (hit rate, Wilson CI, random baseline)", ["report", "--state-dir", str(STATE_DIR)])

    _run("5. verify (hash chain intact)", ["verify", "--state-dir", str(STATE_DIR)])

    ledger = ledger_path(STATE_DIR)
    print(f"\nledger written to: {ledger}")
    print(f"state dir: {STATE_DIR}")

    # --- tamper demonstration -------------------------------------------------
    lines = ledger.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["expected_reason"] = "rewritten after the fact (oops)"
    lines[0] = json.dumps(tampered)
    ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n== 6. tamper the first event, then verify ==")
    code = cli_main(["verify", "--state-dir", str(STATE_DIR)])
    print("=> verify exit code:", code, "(non-zero = tampering detected)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
