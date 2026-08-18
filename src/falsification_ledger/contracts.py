"""Falsification report contract: schema validation, content IDs, evidence status.

A falsification report is the machine-readable evidence that a pre-registered
claim survived (or did not survive) an independent check.  The contract:

- validates reports against ``schema/falsification-report.schema.json``
  (fail-closed: blockers are returned, never silently tolerated),
- computes a content ID (``sha256:<digest>``) over the canonical bytes so
  reports are addressable and tamper-evident,
- classifies evidence status for gates: ``valid`` / ``invalid`` /
  ``missing`` (a falsified or inconsistent report counts as *missing*
  evidence — absence of proof is not proof of absence, but it is not
  support either).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_FILE = "falsification-report.schema.json"
SCHEMA_VERSION = "falsification_ledger.falsification_report.v1"
DOMAIN_PREFIX = "falsification-ledger/falsification-report.v1"
CONSISTENCY_TOLERANCE = 0.005

DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schema" / SCHEMA_FILE

_schema_cache: dict[str, Any] | None = None


def load_falsification_schema(schema_path: Path | str | None = None) -> dict[str, Any]:
    """Load and sanity-check the falsification report schema (cached)."""
    global _schema_cache
    if _schema_cache is None or schema_path is not None:
        path = Path(schema_path) if schema_path is not None else DEFAULT_SCHEMA_PATH
        schema = json.loads(path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        _schema_cache = schema
    return _schema_cache


def falsification_object_id(value: dict[str, Any]) -> str:
    """Content ID: sha256(domain_prefix || 0x00 || canonical bytes)."""
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256(
        DOMAIN_PREFIX.encode("utf-8") + b"\x00" + payload
    ).hexdigest()
    return f"sha256:{digest}"


def validate_falsification_report(
    value: dict[str, Any],
    schema_path: Path | str | None = None,
) -> list[str]:
    """Return blockers; an empty list means the report conforms to the contract."""
    schema = load_falsification_schema(schema_path)
    validator = jsonschema.Draft202012Validator(schema)
    blockers: list[str] = []
    for error in sorted(validator.iter_errors(value), key=lambda e: list(e.path)):
        path = "/".join(str(p) for p in error.path) or "$"
        blockers.append(f"{path}: {error.message}")
    if not blockers and value.get("schema_version") != SCHEMA_VERSION:
        blockers.append(f"schema_version mismatch: {value.get('schema_version')!r}")
    if not blockers:
        consistency = value.get("consistency")
        if consistency is not None:
            if consistency.get("tolerance") != CONSISTENCY_TOLERANCE:
                blockers.append(
                    f"consistency.tolerance must be {CONSISTENCY_TOLERANCE}, "
                    f"got {consistency.get('tolerance')!r}"
                )
    return blockers


def evidence_status(
    value: dict[str, Any],
    schema_path: Path | str | None = None,
) -> str:
    """Evidence status for gates (fail-closed).

    - ``invalid``  — report does not conform to the contract, or the
      conclusion is falsified, or consistency is explicitly broken.
    - ``missing``  — inconclusive: treated as absent evidence.
    - ``valid``    — conformant, not falsified, consistent.
    """
    blockers = validate_falsification_report(value, schema_path)
    if blockers:
        return "invalid"
    conclusion = value.get("conclusion")
    if conclusion == "falsified":
        return "invalid"
    if conclusion == "inconclusive":
        return "missing"
    consistency = value.get("consistency")
    if consistency is not None and consistency.get("consistent") is False:
        return "invalid"
    return "valid"
