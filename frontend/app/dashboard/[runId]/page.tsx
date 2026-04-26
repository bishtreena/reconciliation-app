"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { SummaryCards } from "@/components/SummaryCards";
import { NarrativeSummary } from "@/components/NarrativeSummary";
import { GapBreakdown } from "@/components/GapBreakdown";
import { GapTable } from "@/components/GapTable";
import { getResults } from "@/lib/api";
import type { ResultsResponse } from "@/lib/api";

// ── Skeleton ───────────────────────────────────────────────────────────────

function DashboardSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* SummaryCards skeleton */}
      <div className="grid gap-4 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="rounded-xl border bg-card p-6 space-y-3">
            <div className="h-3 w-24 rounded bg-muted" />
            <div className="h-7 w-32 rounded bg-muted" />
            <div className="h-3 w-20 rounded bg-muted" />
          </div>
        ))}
      </div>
      {/* Narrative skeleton */}
      <div className="rounded-lg border bg-blue-50/60 p-4 space-y-2">
        <div className="h-3 w-full rounded bg-muted" />
        <div className="h-3 w-4/5 rounded bg-muted" />
        <div className="h-3 w-3/5 rounded bg-muted" />
      </div>
      {/* Chart skeleton */}
      <div className="rounded-xl border bg-card p-6">
        <div className="h-4 w-40 rounded bg-muted mb-4" />
        <div className="h-40 w-full rounded bg-muted" />
      </div>
      {/* Table skeleton */}
      <div className="rounded-xl border bg-card p-6 space-y-3">
        <div className="h-4 w-32 rounded bg-muted" />
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="h-10 w-full rounded bg-muted" />
        ))}
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function DashboardPage({
  params,
}: {
  params: { runId: string };
}) {
  const router = useRouter();
  const runId = parseInt(params.runId, 10);

  const [data, setData] = useState<ResultsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (isNaN(runId)) {
      setError("Invalid run ID.");
      setLoading(false);
      return;
    }

    getResults(runId)
      .then((res) => {
        setData(res);
      })
      .catch((err) => {
        const status = err?.response?.status;
        const detail = err?.response?.data?.detail;
        const msg =
          status === 404
            ? `Run #${runId} was not found. It may have been cleared or the URL is incorrect.`
            : status === 400
            ? detail ?? "This run has not been reconciled yet."
            : detail ?? err?.message ?? "Failed to load reconciliation results.";
        setError(String(msg));
      })
      .finally(() => setLoading(false));
  }, [runId]);

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="mb-6 flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            className="gap-1.5"
            onClick={() => router.push("/")}
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">
              Reconciliation Report
            </h1>
            <p className="text-xs text-muted-foreground">Run #{params.runId}</p>
          </div>
        </div>

        {/* Loading */}
        {loading && <DashboardSkeleton />}

        {/* Error */}
        {!loading && error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Could not load results</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* Content */}
        {!loading && data && (
          <div className="space-y-6">
            <SummaryCards summary={data.summary} />
            <NarrativeSummary narrative={data.summary.narrative} />
            <GapBreakdown
              breakdown={data.summary.gap_breakdown}
              roundingDriftTotal={data.summary.rounding_drift_total}
            />
            <GapTable gaps={data.gaps} />
          </div>
        )}
      </div>
    </main>
  );
}