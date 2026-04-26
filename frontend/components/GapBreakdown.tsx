"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatInr, formatInrCompact } from "@/lib/utils";
import type { GapBreakdown as GapBreakdownItem } from "@/lib/api";

// ── Constants ──────────────────────────────────────────────────────────────

const GAP_COLORS: Record<string, string> = {
  TIMING_CROSS_MONTH: "#f59e0b",  // amber
  DUPLICATE_PLATFORM: "#8b5cf6",  // purple
  DUPLICATE_BANK:     "#8b5cf6",  // purple
  ORPHAN_REFUND:      "#ef4444",  // red
  UNKNOWN:            "#f43f5e",  // rose
  ROUNDING_DRIFT:     "#3b82f6",  // blue
};

const GAP_LABELS: Record<string, string> = {
  TIMING_CROSS_MONTH: "Timing",
  DUPLICATE_PLATFORM: "Dup (Platform)",
  DUPLICATE_BANK:     "Dup (Bank)",
  ORPHAN_REFUND:      "Orphan Refund",
  UNKNOWN:            "Unknown",
  ROUNDING_DRIFT:     "Rounding Drift",
};

// ── Tooltip ────────────────────────────────────────────────────────────────

function CustomTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: ChartRow; value: number }>;
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-background px-3 py-2 shadow-md text-sm">
      <p className="font-medium">{row.label}</p>
      <p className="text-muted-foreground">
        {formatInr(row.amount)} · {row.count} gap{row.count !== 1 ? "s" : ""}
      </p>
    </div>
  );
}

// ── Types ──────────────────────────────────────────────────────────────────

interface ChartRow {
  gap_type: string;
  label: string;
  amount: number;
  count: number;
}

interface GapBreakdownProps {
  breakdown: GapBreakdownItem[];
  roundingDriftTotal: number;
}

// ── Component ──────────────────────────────────────────────────────────────

export function GapBreakdown({ breakdown, roundingDriftTotal }: GapBreakdownProps) {
  const chartData: ChartRow[] = breakdown.map((item) => ({
    gap_type: item.gap_type,
    label: GAP_LABELS[item.gap_type] ?? item.gap_type,
    amount: Math.abs(item.total_amount),
    count: item.count,
  }));

  // Inject rounding drift as a synthetic bar if material
  if (roundingDriftTotal > 0.005) {
    chartData.push({
      gap_type: "ROUNDING_DRIFT",
      label: "Rounding Drift",
      amount: roundingDriftTotal,
      count: 0,
    });
  }

  if (chartData.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-semibold">Gap Breakdown</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No classified gaps to display.</p>
        </CardContent>
      </Card>
    );
  }

  const barHeight = 48;
  const chartHeight = Math.max(chartData.length * barHeight + 40, 120);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base font-semibold">Gap Breakdown by Type</CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <ResponsiveContainer width="100%" height={chartHeight}>
          <BarChart
            layout="vertical"
            data={chartData}
            margin={{ top: 4, right: 24, left: 0, bottom: 4 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              horizontal={false}
              stroke="hsl(var(--border))"
            />
            <XAxis
              type="number"
              tickFormatter={(v: number) => formatInrCompact(v)}
              tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="label"
              width={112}
              tick={{ fontSize: 12, fill: "hsl(var(--foreground))" }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: "hsl(var(--muted)/0.3)" }} />
            <Bar dataKey="amount" radius={[0, 4, 4, 0]} maxBarSize={28}>
              {chartData.map((entry) => (
                <Cell
                  key={entry.gap_type}
                  fill={GAP_COLORS[entry.gap_type] ?? "#9ca3af"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>

        {/* Legend */}
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
          {chartData.map((entry) => (
            <span key={entry.gap_type} className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span
                className="inline-block h-2.5 w-2.5 rounded-sm"
                style={{ backgroundColor: GAP_COLORS[entry.gap_type] ?? "#9ca3af" }}
              />
              {entry.label}
            </span>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}