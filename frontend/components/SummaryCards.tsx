"use client";

import { TrendingDown, TrendingUp, Minus } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatInr } from "@/lib/utils";
import type { ReconSummary } from "@/lib/api";

interface SummaryCardsProps {
  summary: ReconSummary;
}

export function SummaryCards({ summary }: SummaryCardsProps) {
  const gapIsZero = Math.abs(summary.total_gap_amount) < 0.01;

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {/* Platform Total */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Platform Total
          </CardTitle>
          <TrendingUp className="h-4 w-4 text-muted-foreground/60" />
        </CardHeader>
        <CardContent>
          <p className="text-2xl font-bold tracking-tight">
            {formatInr(summary.platform_total)}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {summary.total_platform_txns.toLocaleString("en-IN")} transactions
          </p>
        </CardContent>
      </Card>

      {/* Bank Total */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Bank Total
          </CardTitle>
          <TrendingDown className="h-4 w-4 text-muted-foreground/60" />
        </CardHeader>
        <CardContent>
          <p className="text-2xl font-bold tracking-tight">
            {formatInr(summary.bank_total)}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {summary.total_bank_settlements.toLocaleString("en-IN")} settlements
          </p>
        </CardContent>
      </Card>

      {/* Gap */}
      <Card
        className={
          gapIsZero
            ? "border-emerald-200 bg-emerald-50/50 dark:border-emerald-800 dark:bg-emerald-950/20"
            : "border-rose-200 bg-rose-50/50 dark:border-rose-800 dark:bg-rose-950/20"
        }
      >
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle
            className={`text-xs font-medium uppercase tracking-wider ${
              gapIsZero ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"
            }`}
          >
            Reconciliation Gap
          </CardTitle>
          <Minus
            className={`h-4 w-4 ${
              gapIsZero ? "text-emerald-500" : "text-rose-500"
            }`}
          />
        </CardHeader>
        <CardContent>
          <p
            className={`text-2xl font-bold tracking-tight ${
              gapIsZero
                ? "text-emerald-700 dark:text-emerald-400"
                : "text-rose-700 dark:text-rose-400"
            }`}
          >
            {gapIsZero ? "Balanced" : formatInr(Math.abs(summary.total_gap_amount))}
          </p>
          <p
            className={`mt-1 text-xs ${
              gapIsZero ? "text-emerald-600/80" : "text-rose-600/80"
            }`}
          >
            {gapIsZero
              ? "Platform and bank are in agreement"
              : `${summary.total_gaps} gap${summary.total_gaps !== 1 ? "s" : ""} classified`}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}