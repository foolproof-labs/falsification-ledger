# falsification-ledger

A hash-chained, append-only ledger for research claims: **pre-register the
hypothesis and the evidence that would kill it *before* the study runs**,
then adjudicate honestly and measure your hit rate against a random
baseline. Python 3.11+, one dependency (`jsonschema`), Windows / Linux /
macOS.

**Status:** v0.1 —alpha. The ledger semantics are distilled from a
production research pipeline, but this standalone package is new: expect the
CLI and schemas to shift before v1.0.

## Why this exists

Quantitative research has a self-deception problem: you test 500 factor
ideas, remember the 3 that worked, and forget the 497 that died. By the time
you "validate" the lucky survivors, the evidence is already contaminated by
what you saw. Every backtest-hygiene tool on the market attacks the
*statistics* of this problem (deflated Sharpe, PBO, multiple-testing
corrections). `falsification-ledger` attacks the *process*: it makes you
write down, before seeing evidence:

- what you expect (`support` / `against` / `uncertain`), and
- what evidence would **kill** your claim (the falsification contract).

Then it keeps the receipts. Every event lands in an append-only JSONL
**hash chain** —any edit after the fact is detected by `fl verify` —and
the report answers the only question that matters: *do your pre-registered
beliefs actually hit, or is your hit rate indistinguishable from a random
baseline?* (Wilson 95% CI vs the most common actual verdict.)

## Philosophy

**Research is a promise; the ledger keeps it.**

- **Falsifiability is the default, not the exception.** Popper's criterion
  —a claim is scientific only if something could count against it —is
  usually invoked as a lecture. Here it is a required JSON field
  (`falsification_contract` on `preregister`).
- **Pre-analysis plans have known costs and benefits.** [Olken (2015),
  "Promises and Perils of Pre-Analysis Plans"](https://www.aeaweb.org/articles?id=10.1257/jep.29.3.61)
  (JEP 29(3)) documents both; this tool implements the benefits (frozen
  expectations, audit trail) while keeping the costs explicit (`uncertain`
  verdicts and exploratory source types are first-class, so you can register
  what you genuinely do not know).
- **Moderation beats total freezing.** [Banerjee & Duflo, "In Praise of
  Moderation"](https://www.semanticscholar.org/paper/05ecf99a05419f0a268fe885be11a2cf4a8dbd46)
  argue for layered pre-registration; `source_type` (paper / business /
  cross_domain / pipeline / other) exists so confirmatory and exploratory
  claims are never mixed in the same bucket.
- **Finance can become scientific.** [López de Prado (2023), *Causal Factor
  Investing*](https://www.cambridge.org/core/elements/causal-factor-investing/9AFE270D7099B787B8FD4F4CBADE0C6E)
  asks whether factor investing can become a science; this ledger is one
  concrete answer —evidence with a chain of custody, adjudicated against a
  pre-registered expectation.
- **Automated research needs machine-checkable evidence.** [EviBound
  (arXiv:2511.05524)](https://ar5iv.labs.arxiv.org/html/2511.05524) and
  [ECLIPSE v2.0](https://ideas.repec.org/p/osf/metaar/z3fke_v1.html) argue
  that agentic research pipelines must eliminate false claims through
  verifiable evidence; `fl submit` validates falsification reports against a
  JSON Schema and computes content IDs, so gates can trust the evidence
  without trusting the messenger.

## Quick start

```bash
# install from PyPI (once published)
pip install falsification-ledger

# or run without installing anything:
#   PYTHONPATH=src python -m falsification_ledger --help

# try the full loop on a scratch ledger (creates files under a temp dir)
python examples/demo.py
```

The manual loop:

```bash
fl init --state-dir ~/.research-ledger

# 1. BEFORE running the study: register what you expect,
#    and what evidence would kill the claim.
fl preregister --state-dir ~/.research-ledger \
  --case-id MOMENTUM-OOS-2026Q3 \
  --verdict support \
  --reason "momentum rank IC stays positive OOS" \
  --source-type paper \
  --contract kill-criteria.json

# 2. When an independent check produces evidence, submit it:
fl submit --report falsification-report.json
# -> {"content_id": "sha256:...", "evidence_status": "valid", ...}

# 3. AFTER the study: adjudicate honestly.
fl adjudicate --state-dir ~/.research-ledger \
  --case-id MOMENTUM-OOS-2026Q3 --verdict support

# 4. Measure whether you are better than a coin flip.
fl report --state-dir ~/.research-ledger --min-cases 20

# 5. Any time: prove nobody rewrote history.
fl verify --state-dir ~/.research-ledger
```

## Commands

| Command | What it does |
| --- | --- |
| `init` | Create the ledger state directory |
| `preregister` | Register a claim: `--case-id`, `--verdict` (support/against/uncertain), `--reason`, optional `--source-type`, optional `--contract` (falsification contract JSON). Duplicate registration for the same case is rejected |
| `submit` | Validate a falsification report against the contract schema; print its content ID (`sha256:...`) and evidence status (`valid` / `invalid` / `missing`). Read-only; exits non-zero on blockers |
| `adjudicate` | Backfill the actual verdict for a registered case (register required; once per case) |
| `report` | Hit-rate report: resolved cases, completeness, participation, hit rate with **Wilson 95% CI**, random baseline, per-source-type breakdown, `verdict_ready` gate |
| `verify` | Recompute the hash chain of the whole ledger; detects any edit, insertion, or reordering |
| `version` | Print version |

Global flag: `--state-dir` on every stateful command (default: none —the
ledger path is always explicit, so a `git add .` can never sweep it into
version control).

## Ledger format

The ledger is a JSONL file at `<state-dir>/ledger.jsonl`. Every line is one
event:

```json
{"schema_version": "falsification_ledger.prediction_event.v1",
 "event": "register", "record_id": "...", "case_id": "CASE-1",
 "expected_verdict": "support", "expected_reason": "...",
 "source_type": "paper", "falsification_contract": {...},
 "actual_verdict": null, "recorded_at": "...", "concluded_at": null,
 "prev_hash": null,
 "event_hash": "sha256(prev_hash || 0x00 || canonical payload)"}
```

`verify` recomputes every `event_hash` and checks each `prev_hash` link.
**Any tampering —editing a reason, deleting a line, reordering events —breaks the chain at a specific line number.**

## Falsification reports

A falsification report is the machine-readable evidence produced by an
independent check (null-model randomization, OOS rank IC, FDR correction,
protocol deviation, effect CI, cost sensitivity, ...). The contract:

- schema: [`schema/falsification-report.schema.json`](https://github.com/foolproof-labs/falsification-ledger/blob/main/schema/falsification-report.schema.json)
  (draft 2020-12, `additionalProperties: false`, fail-closed);
- content ID: `sha256:` over `domain-prefix || 0x00 || canonical JSON` —  the same report always yields the same ID, a one-field change yields a
  different ID;
- evidence status (fail-closed for gates):
  - `valid` —conformant, conclusion `not_falsified`, consistency intact;
  - `invalid` —non-conformant, or conclusion `falsified`, or explicitly
    inconsistent;
  - `missing` —conclusion `inconclusive`: treated as *absent* evidence.

## Verification model

`fl verify` is the tamper-evidence layer: it re-derives the entire chain
from the file bytes and reports the first bad line. Combined with
`preregister` (frozen expectations) and `submit` (content-addressed
evidence), a research pipeline can prove to itself —and to reviewers —that the expectation existed before the evidence did. Nothing here trades,
prices, or decides.

## Development

```bash
python -m pip install -e . pytest
python -m pytest
```

CI runs the full test suite on Ubuntu, Windows and macOS with Python 3.11
and 3.12. Issues are handled on weekends; pull requests are welcome.

## Related work

- [Olken (2015), Promises and Perils of Pre-Analysis Plans](https://www.aeaweb.org/articles?id=10.1257/jep.29.3.61) —the economics of freezing expectations
- [Banerjee & Duflo, In Praise of Moderation](https://www.semanticscholar.org/paper/05ecf99a05419f0a268fe885be11a2cf4a8dbd46) —layered pre-registration
- [López de Prado (2023), Causal Factor Investing](https://www.cambridge.org/core/elements/causal-factor-investing/9AFE270D7099B787B8FD4F4CBADE0C6E) —can factor investing become scientific?
- [EviBound: Evidence-Bound Autonomous Research (arXiv:2511.05524)](https://ar5iv.labs.arxiv.org/html/2511.05524) —governance for agentic research
- [ECLIPSE v2.0: A Systematic Falsification Framework](https://ideas.repec.org/p/osf/metaar/z3fke_v1.html) —enforce falsifiability integrity

## Project family

Part of [Foolproof Labs](https://github.com/foolproof-labs) — a toolchain
against self-deception in quantitative research:

- [pit-adjuster](https://github.com/foolproof-labs/pit-adjuster) — PIT back-adjustment with static forward-adjustment drift detection
- [falsification-ledger](https://github.com/foolproof-labs/falsification-ledger) — pre-registration and falsification ledger
- [factor-qc](https://github.com/foolproof-labs/factor-qc) — fail-closed backtest quality gate
- [lesson-book](https://github.com/foolproof-labs/lesson-book) — tuition memory for traders
- [lookahead-free](https://github.com/foolproof-labs/lookahead-free) — verifiable look-ahead-freedom checks
- [ashare-data-immunity](https://github.com/foolproof-labs/ashare-data-immunity) — data immunity for A-share daily bars

## License

MIT
