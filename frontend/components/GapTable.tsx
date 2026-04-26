"use client";

import { useState, useMemo } from "react";
import { ChevronDown, ChevronUp, ChevronsUpDown, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatInr, formatDate } from "@/lib/utils";
import type { GapResultOut } from "@/lib/api";

// ── Gap type metadata ──────────────────────────────────────────────────────

const GAP_META: Record<string, { label: string; className: string }> = {
  TIMING_CROSS_MONTH: {
    label: "Timing",
    className: "border-amber-300 bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300",
  },
  DUPLICATE_PLATFORM: {
    label: "Dup · Platform",
    className: "border-purple-300 bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300",
  },
  DUPLICATE_BANK: {
    label: "Dup · Bank",
    className: "border-purple-300 bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300",
  },
  ORPHAN_REFUND: {
    label: "Orphan Refund",
    className: "border-rose-300 bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-300",
  },
  UNKNOWN: {
    label: "Unknown",
    className: "border-gray-300 bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
  },
};

function GapBadge({ gapType }: { gapType: string }) {
  const meta = GAP_META[gapType] ?? {
    label: gapType,
    className: "border-gray-300 bg-gray-100 text-gray-700",
  };
  return (
    <Badge variant="outline" className={meta.className}>
      {meta.label}
    </Badge>
  );
}

// ── Row helpers ────────────────────────────────────────────────────────────

function getIdentifier(row: GapResultOut): string {
  const src = row.source_row_json;
  if (!src) return `#${row.id}`;
  return (
    (src.txn_id as string) ??
    (src.settlement_id as string) ??
    (src.reference_id as string) ??
    `#${row.id}`
  );
}

function getDate(row: GapResultOut): string {
  const src = row.source_row_json;
  if (!src) return "—";
  return formatDate(src.timestamp ?? src.settlement_date);
}

// ── Sort helpers ───────────────────────────────────────────────────────────

type SortKey = "gap_type" | "amount" | "confidence";
type SortDir = "asc" | "desc";

function SortIcon({ col, active, dir }: { col: string; active: string; dir: SortDir }) {
  if (col !== active)
    return <ChevronsUpDown className="ml-1 inline h-3.5 w-3.5 text-muted-foreground/50" />;
  return dir === "asc"
    ? <ChevronUp className="ml-1 inline h-3.5 w-3.5" />
    : <ChevronDown className="ml-1 inline h-3.5 w-3.5" />;
}

// ── Filter pills ───────────────────────────────────────────────────────────

const ALL = "__all__";

// ── Main component ─────────────────────────────────────────────────────────

interface GapTableProps {
  gaps: Record<string, GapResultOut[]>;
}

export function GapTable({ gaps }: GapTableProps) {
  const allRows: GapResultOut[] = useMemo(
    () => Object.values(gaps).flat(),
    [gaps]
  );
  const gapTypes = useMemo(
    () => Array.from(new Set(allRows.map((r) => r.gap_type))).sort(),
    [allRows]
  );

  const [filter, setFilter] = useState<string>(ALL);
  const [sortKey, setSortKey] = useState<SortKey>("amount");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const toggleExpand = (id: number) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) { next.delete(id); } else { next.add(id); }
      return next;
    });

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const filtered = useMemo(
    () => (filter === ALL ? allRows : allRows.filter((r) => r.gap_type === filter)),
    [allRows, filter]
  );

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      let cmp = 0;
      if (sortKey === "amount") {
        cmp = (a.amount ?? 0) - (b.amount ?? 0);
      } else if (sortKey === "gap_type") {
        cmp = a.gap_type.localeCompare(b.gap_type);
      } else if (sortKey === "confidence") {
        cmp = (a.classification_confidence ?? -1) - (b.classification_confidence ?? -1);
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [filtered, sortKey, sortDir]);

  if (allRows.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">Gap Details</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No gap rows to display.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-base font-semibold">
            Gap Details
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              ({sorted.length} of {allRows.length})
            </span>
          </CardTitle>

          {/* Filter pills */}
          <div className="flex flex-wrap gap-1.5">
            <Button
              size="sm"
              variant={filter === ALL ? "default" : "outline"}
              className="h-7 px-2.5 text-xs"
              onClick={() => setFilter(ALL)}
            >
              All
            </Button>
            {gapTypes.map((t) => (
              <Button
                key={t}
                size="sm"
                variant={filter === t ? "default" : "outline"}
                className="h-7 px-2.5 text-xs"
                onClick={() => setFilter(t)}
              >
                {GAP_META[t]?.label ?? t}
              </Button>
            ))}
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-8 pl-4" />
              <TableHead
                className="cursor-pointer select-none"
                onClick={() => handleSort("gap_type")}
              >
                Type <SortIcon col="gap_type" active={sortKey} dir={sortDir} />
              </TableHead>
              <TableHead
                className="cursor-pointer select-none text-right"
                onClick={() => handleSort("amount")}
              >
                Amount <SortIcon col="amount" active={sortKey} dir={sortDir} />
              </TableHead>
              <TableHead>Identifier</TableHead>
              <TableHead>Date</TableHead>
              <TableHead
                className="cursor-pointer select-none text-right"
                onClick={() => handleSort("confidence")}
              >
                Confidence <SortIcon col="confidence" active={sortKey} dir={sortDir} />
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((row) => {
              const isExpanded = expanded.has(row.id);
              const hasReasoning = !!row.llm_reasoning;
              return [
                <TableRow
                  key={row.id}
                  className={hasReasoning ? "cursor-pointer" : undefined}
                  onClick={() => hasReasoning && toggleExpand(row.id)}
                >
                  {/* Expand toggle */}
                  <TableCell className="pl-4 pr-0">
                    {hasReasoning ? (
                      <ChevronRight
                        className={`h-4 w-4 text-muted-foreground transition-transform duration-150 ${
                          isExpanded ? "rotate-90" : ""
                        }`}
                      />
                    ) : null}
                  </TableCell>

                  <TableCell>
                    <GapBadge gapType={row.gap_type} />
                  </TableCell>

                  <TableCell className="text-right font-mono text-sm">
                    {row.amount != null ? formatInr(Math.abs(row.amount)) : "—"}
                  </TableCell>

                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {getIdentifier(row)}
                  </TableCell>

                  <TableCell className="text-sm text-muted-foreground">
                    {getDate(row)}
                  </TableCell>

                  <TableCell className="text-right text-sm">
                    {row.classification_confidence != null ? (
                      <span
                        className={
                          row.classification_confidence >= 0.8
                            ? "text-emerald-600 dark:text-emerald-400"
                            : row.classification_confidence >= 0.5
                            ? "text-amber-600 dark:text-amber-400"
                            : "text-rose-600 dark:text-rose-400"
                        }
                      >
                        {Math.round(row.classification_confidence * 100)}%
                      </span>
                    ) : (
                      <span className="text-muted-foreground/50">—</span>
                    )}
                  </TableCell>
                </TableRow>,

                /* Expanded reasoning row */
                isExpanded && hasReasoning ? (
                  <TableRow key={`${row.id}-expanded`} className="hover:bg-transparent">
                    <TableCell colSpan={6} className="pb-3 pl-10 pt-0">
                      <div className="rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
                        <span className="mr-1.5 font-medium text-foreground">
                          LLM reasoning:
                        </span>
                        {row.llm_reasoning}
                      </div>
                    </TableCell>
                  </TableRow>
                ) : null,
              ];
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}