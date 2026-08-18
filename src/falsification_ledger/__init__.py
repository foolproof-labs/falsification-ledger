"""falsification-ledger: pre-registration and falsification ledger.

A hash-chained, append-only JSONL ledger for research claims: register the
hypothesis and the evidence that would kill it *before* running the study,
submit evidence, adjudicate, and report hit-rate with a Wilson confidence
interval against a random baseline. Every event is content-addressed and
chain-verified; nothing here trades, prices, or decides.
"""

from .contracts import (
    evidence_status,
    falsification_object_id,
    load_falsification_schema,
    validate_falsification_report,
)
from .ledger import (
    conclude_prediction,
    ensure_prediction_registered,
    has_prediction_registered,
    ledger_path,
    register_prediction,
    report_prediction_hitrate,
    verify_chain,
)

__version__ = "0.1.1"

__all__ = [
    "conclude_prediction",
    "ensure_prediction_registered",
    "evidence_status",
    "falsification_object_id",
    "has_prediction_registered",
    "ledger_path",
    "load_falsification_schema",
    "register_prediction",
    "report_prediction_hitrate",
    "validate_falsification_report",
    "verify_chain",
]

