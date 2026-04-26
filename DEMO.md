# Recon — 2-Minute Demo Script

_Read this aloud while recording. Estimated pace: ~130 wpm. Total: ~2 min._

---

## [0:00 — 0:10] Opening

"Hi — this is Recon, a payments reconciliation tool I built to replace the
manual Excel process our finance team runs every month. The goal: upload two
CSVs and get an instant breakdown of every discrepancy between what the payment
platform recorded and what the bank actually settled."

---

## [0:10 — 0:25] The upload page

_Show the upload page at localhost:3000._

"This is the upload page. You can drag-and-drop your own platform export and
bank settlement file, or — for this demo — click 'Use sample data' to load the
January 2026 dataset I pre-generated. It contains 872 platform transactions and
871 bank settlements with four types of real-world gaps planted inside."

_Click 'Use sample data'. Both drop zones fill with filenames._

---

## [0:25 — 0:40] Pipeline running

_The loading banner appears: 'Uploading files…' → 'Running reconciliation pipeline…'_

"The button disables and shows exactly which stage we're on. Behind the scenes
the backend ingests the CSVs, runs the matching engine, classifies every gap by
type using rule-based logic, and generates a narrative summary. The whole
pipeline takes about three seconds."

_The page redirects automatically to the dashboard._

---

## [0:40 — 1:00] Summary cards

_Point to the three cards at the top._

"At the top we get three key numbers: platform total, bank total, and the net
reconciliation gap. Here the bank total is slightly higher — that's because a
bank-side duplicate inflated the bank's reported volume. The gap card turns
red when there's a discrepancy, green when everything balances."

---

## [1:00 — 1:15] Narrative

_Point to the blue narrative block._

"Below that is a plain-English executive summary written by the template engine
— no jargon, just the facts a CFO needs: the size of each gap category and what
action is required. In production this would come from a live Claude call."

---

## [1:15 — 1:35] Gap breakdown chart

_Point to the horizontal bar chart._

"This chart shows the monetary exposure by gap type. Timing gaps — transactions
from January 30–31 whose bank settlement landed in February — make up the
largest slice at ₹3.7L. Orphan refunds add another ₹1.25L. Rounding drift is
tiny in total but material for audit: 200 bank settlements settled one-to-five
paise short of the platform amount, for a cumulative drift of exactly ₹6."

---

## [1:35 — 1:55] Gap table

_Point to the table. Click a filter pill, then click a column header, then
expand a row._

"The table lists every classified gap row. I can filter to a single type with
these pills, sort by amount or confidence, and expand any row to read the
classification reasoning. Confidence is colour-coded: green for high, amber for
medium, red for low — so the reviewer knows where to focus first."

---

## [1:55 — 2:00] Close

"That's it — from two raw CSV files to a fully classified, interactive
reconciliation report in under five seconds. Thanks for watching."

---

## Before you record: start commands

```bash
# Terminal 1 — backend
cd recon/backend
py -m uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload

# Terminal 2 — frontend
cd recon/frontend
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to begin.

> The server logs will print per-stage timing (matching / classify / aggregate /
> narrate) so you can see exactly where time is spent while the pipeline runs.