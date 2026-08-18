"""Command-line interface for falsification-ledger.

Subcommands:

- ``init``                 create the ledger state directory
- ``preregister``          register a claim (verdict + reason) before evidence;
                           optionally attach a falsification contract JSON
- ``submit``               validate a falsification report and print its
                           content ID and evidence status (read-only)
- ``adjudicate``           backfill the actual verdict for a case
- ``report``               hit-rate report (Wilson 95% CI vs random baseline)
- ``verify``               hash-chain integrity check of the whole ledger
- ``version``              print version
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .contracts import evidence_status, falsification_object_id, validate_falsification_report
from .ledger import (
    conclude_prediction,
    ledger_path,
    register_prediction,
    report_prediction_hitrate,
    verify_chain,
)


def _print_json(body: dict[str, Any]) -> None:
    print(json.dumps(body, ensure_ascii=False, indent=2))


def _load_json_file(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fl",
        description="Pre-registration and falsification ledger for research.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create the ledger state directory")
    init.add_argument("--state-dir", required=True, help="ledger state directory")

    prereg = sub.add_parser("preregister", help="register a claim before evidence")
    prereg.add_argument("--state-dir", required=True)
    prereg.add_argument("--case-id", required=True)
    prereg.add_argument(
        "--verdict", required=True, choices=["support", "against", "uncertain"]
    )
    prereg.add_argument("--reason", required=True)
    prereg.add_argument("--source-type", default="other",
                        choices=["paper", "business", "cross_domain", "pipeline", "other"])
    prereg.add_argument("--contract", default=None,
                        help="falsification contract JSON: what evidence would kill the claim")

    submit = sub.add_parser("submit", help="validate a falsification report (read-only)")
    submit.add_argument("--report", required=True, help="falsification report JSON path")
    submit.add_argument("--schema", default=None, help="override schema JSON path")

    adjudicate = sub.add_parser("adjudicate", help="backfill the actual verdict")
    adjudicate.add_argument("--state-dir", required=True)
    adjudicate.add_argument("--case-id", required=True)
    adjudicate.add_argument(
        "--verdict", required=True, choices=["support", "against", "uncertain"]
    )

    report = sub.add_parser("report", help="hit-rate report")
    report.add_argument("--state-dir", required=True)
    report.add_argument("--min-cases", type=int, default=20)

    verify = sub.add_parser("verify", help="hash-chain integrity check")
    verify.add_argument("--state-dir", required=True)

    sub.add_parser("version", help="print version")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0

    if args.command == "init":
        path = ledger_path(args.state_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"init: ledger ready at {path}")
        return 0

    if args.command == "preregister":
        contract = _load_json_file(args.contract) if args.contract else None
        result = register_prediction(
            args.state_dir,
            args.case_id,
            args.verdict,
            args.reason,
            args.source_type,
            falsification_contract=contract,
        )
        _print_json(result)
        return 0

    if args.command == "submit":
        report = _load_json_file(args.report)
        blockers = validate_falsification_report(report, args.schema)
        body = {
            "content_id": falsification_object_id(report),
            "evidence_status": evidence_status(report, args.schema),
            "blockers": blockers,
        }
        _print_json(body)
        return 0 if not blockers else 1

    if args.command == "adjudicate":
        _print_json(conclude_prediction(args.state_dir, args.case_id, args.verdict))
        return 0

    if args.command == "report":
        _print_json(report_prediction_hitrate(args.state_dir, min_cases=args.min_cases))
        return 0

    if args.command == "verify":
        body = verify_chain(args.state_dir)
        _print_json(body)
        return 0 if body.get("ok") else 1

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
