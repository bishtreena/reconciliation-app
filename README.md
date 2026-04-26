# Recon — Payments Reconciliation Tool

## What it does

Recon ingests two CSV exports — a payment platform's transaction ledger and the corresponding bank settlement file — and automatically surfaces every discrepancy between them. It classifies each gap into one of four categories (timing, rounding drift, duplicate, orphan refund), computes aggregate totals, and delivers an interactive dashboard with sortable gap tables, a breakdown chart, and a plain-English executive narrative. The entire pipeline runs in under five seconds on a month's worth of data, replacing a manual Excel process that typically takes hours.

---

## Architecture

```
Browser (Next.js 14)
      │
      │  HTTP / JSON (axios)
      ▼
┌─────────────────────────────────────────┐
│           FastAPI  (app/main.py)        │
│                                         │
│  POST /upload    ──► ingestion.py       │
│  POST /reconcile ──► matching.py        │
│                  ──► classifier.py      │
│                  ──► aggregator.py      │
│                  ──► narrator.py        │
│  GET  /results   ──► aggregator.py      │
│  GET  /sample-data                      │
└────────────────┬────────────────────────┘
                 │  SQLAlchemy ORM
                 ▼
         SQLite  (recon.db)
         ┌──────────────────┐
         │  recon_runs      │
         │  platform_txns   │
         │  bank_settlements│
         │  gap_results     │
         └──────────────────┘
                 ▲
         Anthropic API  (optional)
         claude-sonnet-4-5
         • gap classification fallback
         • narrative generation
```

---

## Data flow

What happens between clicking **Reconcile** and seeing the dashboard:

1. **Upload** (`POST /upload`) — both CSV files are streamed to the server, validated for required columns, coerced to typed values, and bulk-inserted into `platform_txns` and `bank_settlements` under a new `recon_run` row. Returns `run_id`.

2. **Match** (`matching.py`) — duplicates are separated before the join so they don't inflate counts. Bank settlements are filtered to the platform's primary reconciliation month. A left-join on `txn_id = reference_id` produces four buckets: `matched`, `rounding_candidates` (|Δ| ≤ ₹0.10), `unmatched_platform`, `unmatched_bank`.

3. **Classify** (`classifier.py`) — every unmatched row runs through a priority chain of rule-based detectors (duplicate → orphan refund → timing cross-month). Anything that clears all rules is forwarded to Claude for a best-guess classification with a confidence score. All results are persisted as `GapResult` rows.

4. **Aggregate** (`aggregator.py`) — queries the DB to produce signed platform and bank totals, sums rounding-candidate diffs for `rounding_drift_total`, and groups `GapResult` rows into a per-type breakdown dict.

5. **Narrate** (`narrator.py`) — builds a 4–5 sentence executive summary from the aggregate numbers. Uses Claude when `ANTHROPIC_API_KEY` is set; falls back to a deterministic template otherwise.

6. **Respond** — the run's status is set to `completed` and the full `ReconSummary` + grouped gap rows are returned to the frontend, which navigates to `/dashboard/{run_id}`.

---

## Gap types detected

| Type | Definition |
|---|---|
| **TIMING_CROSS_MONTH** | Platform transaction from Jan 30–31 whose bank settlement landed in the first 3 days of the following month; amounts match, timing does not. |
| **DUPLICATE_PLATFORM** | The same `txn_id` appears more than once in the platform export, inflating platform-side volume. |
| **DUPLICATE_BANK** | The same `reference_id` appears more than once in the bank file, inflating bank-side volume. |
| **ORPHAN_REFUND** | A refund row whose `parent_txn_id` does not correspond to any known payment in the platform data. |

---

## Stated assumptions

1. **Currency** — all amounts are INR. Multi-currency reconciliation is not supported.
2. **ID linkage** — bank `reference_id` is assumed to equal the platform `txn_id` for every settlement. Banks that use their own internal reference scheme will produce false unmatched rows.
3. **Rounding tolerance** — a matched pair is classified as rounding drift when `|platform_amount − bank_amount| ≤ ₹0.10`. This threshold is hardcoded and identical for all merchants.
4. **Cross-month window** — a bank settlement is considered a timing gap if it falls within the first 3 calendar days of the month following the platform transaction date. Settlements outside that window are treated as truly unmatched.
5. **Refund linkage** — every refund in the platform export must carry a non-null `parent_txn_id` pointing to the originating payment. Refunds without one are automatically classified as orphans.
6. **Status filter** — only transactions with `status = "success"` are counted toward the platform total. Pending, failed, and cancelled rows are ingested but excluded from reconciliation arithmetic.

---

## Running locally

> **Windows note:** use `--host 127.0.0.1` to avoid a Windows Firewall bind error on port 8000.

### Backend

```bash
cd recon/backend

# Install dependencies (Python 3.11+)
pip install -r requirements.txt

# Optional — enable LLM features
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# Start the API server
py -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload
```

API available at `http://localhost:8080`. Swagger docs at `http://localhost:8080/docs`.

### Frontend

```bash
cd recon/frontend

# Install dependencies
npm install

# Point the frontend at the backend (already set in .env.local)
# NEXT_PUBLIC_API_URL=http://localhost:8080

# Start the dev server
npm run dev
```

Open `http://localhost:3000`.

---

## Generating sample data

```bash
cd recon/backend
py -m app.data_generator
```

Writes `recon/sample_data/platform_transactions.csv` and `bank_settlements.csv` with seed=42. Prints a ground-truth summary of every planted gap so you can verify the pipeline output.

---

## Running tests

```bash
cd recon/backend
py -m pytest tests/test_reconciliation.py -v
```

12 tests covering ingestion row counts, matching bucket sizes, rounding tolerance, full-dataset coverage, and an end-to-end API test with the LLM mocked out.

---

## Known limitations in production

Real bank settlement files rarely use the platform's `txn_id` as the `reference_id` without transformation — most banks apply their own internal numbering or include batch prefixes, which means the current exact-match join will produce large volumes of false unmatched rows until a bank-specific ID normalisation layer is added. The ₹0.10 rounding tolerance is hardcoded globally, but high-value merchants processing crores per transaction and micro-merchants with average ticket sizes under ₹200 need different thresholds; a per-merchant configuration table is required before this can go live for a mixed merchant portfolio. Finally, LLM-classified gaps are written directly to the `gap_results` table with no confidence threshold gate and no human review queue, so a miscategorised gap at low confidence will appear in the dashboard with the same visual weight as a high-confidence rule-based classification, creating silent audit risk.

---

## Project structure

```
recon/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI routes + pipeline orchestration
│   │   ├── models.py        # SQLAlchemy ORM models
│   │   ├── schemas.py       # Pydantic request/response schemas
│   │   ├── ingestion.py     # CSV validation + bulk DB insert
│   │   ├── matching.py      # Pandas join + gap detection
│   │   ├── classifier.py    # Rule-based + LLM gap classification
│   │   ├── aggregator.py    # Totals + breakdown computation
│   │   ├── narrator.py      # Executive summary generation
│   │   └── data_generator.py# Synthetic data with planted gaps
│   ├── tests/
│   │   └── test_reconciliation.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── page.tsx         # Upload page
│   │   ├── error.tsx        # Global error boundary
│   │   └── dashboard/[runId]/
│   │       ├── page.tsx     # Results dashboard
│   │       └── error.tsx    # Dashboard error boundary
│   ├── components/
│   │   ├── SummaryCards.tsx
│   │   ├── GapBreakdown.tsx # Recharts horizontal bar chart
│   │   ├── GapTable.tsx     # Sortable + filterable gap table
│   │   ├── NarrativeSummary.tsx
│   │   └── UploadZone.tsx
│   ├── lib/
│   │   ├── api.ts           # Axios fetchers + TypeScript types
│   │   └── utils.ts         # INR formatter, date formatter, cn()
│   ├── vercel.json
│   └── .env.example
├── sample_data/             # Generated by data_generator.py
├── render.yaml              # Backend deploy config
├── .gitignore
└── DEMO.md
```