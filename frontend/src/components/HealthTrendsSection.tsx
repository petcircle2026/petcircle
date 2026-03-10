"use client";

import { useEffect, useState } from "react";
import type { HealthTrendsData } from "@/lib/api";
import { fetchHealthTrends } from "@/lib/api";

/** Format "2024-03" to "Mar 2024" for display. */
function formatMonth(m: string): string {
  const [year, month] = m.split("-");
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  const idx = parseInt(month, 10) - 1;
  return `${months[idx] || month} ${year}`;
}

/** Short month label for chart axis: "Mar '24" */
function shortMonth(m: string): string {
  const [year, month] = m.split("-");
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  const idx = parseInt(month, 10) - 1;
  return `${months[idx] || month} '${year.slice(2)}`;
}

/** Format YYYY-MM-DD to DD-MM-YYYY. */
function formatDate(d: string): string {
  const parts = d.split("-");
  if (parts.length === 3) return `${parts[2]}-${parts[1]}-${parts[0]}`;
  return d;
}

/** Status badge colors. */
function statusClass(status: string): string {
  const map: Record<string, string> = {
    up_to_date: "bg-green-100 text-green-800",
    upcoming: "bg-yellow-100 text-yellow-800",
    overdue: "bg-red-100 text-red-800",
    incomplete: "bg-orange-100 text-orange-700",
    cancelled: "bg-gray-100 text-gray-500",
  };
  return map[status] || "bg-gray-100 text-gray-600";
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    up_to_date: "Up To Date",
    upcoming: "Upcoming",
    overdue: "Overdue",
    incomplete: "Incomplete",
    cancelled: "Cancelled",
  };
  return map[status] || status;
}

/** Pure SVG bar chart — no external dependencies. */
function BarChart({
  data,
  barColorClass = "fill-blue-500",
}: {
  data: { month: string; items_completed: number }[];
  barColorClass?: string;
}) {
  if (data.length === 0) return null;

  const maxVal = Math.max(...data.map((d) => d.items_completed), 1);
  const chartWidth = 600;
  const chartHeight = 200;
  const barPadding = 4;
  const leftPad = 30;
  const bottomPad = 40;
  const topPad = 10;
  const drawWidth = chartWidth - leftPad;
  const drawHeight = chartHeight - bottomPad - topPad;
  const barWidth = Math.min(
    (drawWidth - barPadding * data.length) / data.length,
    40
  );
  const totalBarsWidth =
    data.length * barWidth + (data.length - 1) * barPadding;
  const startX = leftPad + (drawWidth - totalBarsWidth) / 2;

  // Y-axis gridlines.
  const gridLines = [];
  const gridCount = Math.min(maxVal, 4);
  for (let i = 0; i <= gridCount; i++) {
    const val = Math.round((maxVal / gridCount) * i);
    const y = topPad + drawHeight - (val / maxVal) * drawHeight;
    gridLines.push({ val, y });
  }

  return (
    <svg
      viewBox={`0 0 ${chartWidth} ${chartHeight}`}
      className="w-full"
      preserveAspectRatio="xMidYMid meet"
    >
      {/* Grid lines */}
      {gridLines.map((g) => (
        <g key={g.val}>
          <line
            x1={leftPad}
            y1={g.y}
            x2={chartWidth}
            y2={g.y}
            stroke="#e5e7eb"
            strokeWidth="1"
          />
          <text
            x={leftPad - 4}
            y={g.y + 4}
            textAnchor="end"
            className="fill-gray-400"
            fontSize="10"
          >
            {g.val}
          </text>
        </g>
      ))}

      {/* Bars */}
      {data.map((d, i) => {
        const barHeight = (d.items_completed / maxVal) * drawHeight;
        const x = startX + i * (barWidth + barPadding);
        const y = topPad + drawHeight - barHeight;

        return (
          <g key={d.month}>
            <rect
              x={x}
              y={y}
              width={barWidth}
              height={barHeight}
              rx="3"
              className={barColorClass}
            />
            {/* Value on top of bar */}
            {d.items_completed > 0 && (
              <text
                x={x + barWidth / 2}
                y={y - 4}
                textAnchor="middle"
                className="fill-gray-600"
                fontSize="10"
                fontWeight="600"
              >
                {d.items_completed}
              </text>
            )}
            {/* Month label */}
            <text
              x={x + barWidth / 2}
              y={chartHeight - bottomPad + 14}
              textAnchor="middle"
              className="fill-gray-500"
              fontSize="9"
              transform={`rotate(-30, ${x + barWidth / 2}, ${chartHeight - bottomPad + 14})`}
            >
              {shortMonth(d.month)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** Status summary donut — pure SVG. */
function StatusDonut({ summary }: { summary: HealthTrendsData["status_summary"] }) {
  const segments = [
    { key: "up_to_date", count: summary.up_to_date, color: "#22c55e" },
    { key: "upcoming", count: summary.upcoming, color: "#eab308" },
    { key: "overdue", count: summary.overdue, color: "#ef4444" },
    { key: "incomplete", count: summary.incomplete, color: "#f97316" },
    { key: "cancelled", count: summary.cancelled, color: "#9ca3af" },
  ].filter((s) => s.count > 0);

  const total = segments.reduce((sum, s) => sum + s.count, 0);
  if (total === 0) return null;

  const size = 120;
  const cx = size / 2;
  const cy = size / 2;
  const radius = 45;
  const strokeWidth = 16;
  const circumference = 2 * Math.PI * radius;

  let offset = 0;

  return (
    <div className="flex items-center gap-4">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {segments.map((seg) => {
          const segLen = (seg.count / total) * circumference;
          const el = (
            <circle
              key={seg.key}
              cx={cx}
              cy={cy}
              r={radius}
              fill="none"
              stroke={seg.color}
              strokeWidth={strokeWidth}
              strokeDasharray={`${segLen} ${circumference - segLen}`}
              strokeDashoffset={-offset}
              transform={`rotate(-90, ${cx}, ${cy})`}
            />
          );
          offset += segLen;
          return el;
        })}
        <text
          x={cx}
          y={cy + 4}
          textAnchor="middle"
          className="fill-gray-700"
          fontSize="18"
          fontWeight="700"
        >
          {total}
        </text>
      </svg>
      <div className="flex flex-col gap-1 text-xs">
        {segments.map((seg) => (
          <div key={seg.key} className="flex items-center gap-2">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: seg.color }}
            />
            <span className="text-gray-600">
              {statusLabel(seg.key)}: {seg.count}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

interface Props {
  token: string;
}

export default function HealthTrendsSection({ token }: Props) {
  const [trends, setTrends] = useState<HealthTrendsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        setLoading(true);
        const data = await fetchHealthTrends(token);
        if (!cancelled) setTrends(data);
      } catch (e: any) {
        if (!cancelled) setError(e.message || "Failed to load trends.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (loading) {
    return (
      <div className="rounded-lg border bg-white p-6 text-center text-gray-400">
        Loading health trends...
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border bg-white p-6 text-center text-red-400 text-sm">
        {error}
      </div>
    );
  }

  if (!trends) return null;

  const hasCompletions = trends.monthly_completions.length > 0;
  const hasTimeline = trends.item_timeline.length > 0;
  const hasDiagnostics = (trends.diagnostic_trends || []).length > 0;
  const hasVaccineMetrics = (trends.vaccine_metrics?.monthly_vaccinations || []).length > 0;

  // Transform diagnostic_trends into the shape BarChart expects.
  const diagnosticBarData = (trends.diagnostic_trends || []).map((d) => ({
    month: d.month,
    items_completed: d.count,
  }));

  const vaccineBarData = (trends.vaccine_metrics?.monthly_vaccinations || []).map((d) => ({
    month: d.month,
    items_completed: d.count,
  }));

  if (!hasCompletions && !hasTimeline) {
    return (
      <div className="rounded-lg border bg-white p-6 text-center text-gray-400">
        No health activity recorded yet. Update your preventive records to see trends here.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top row: Status summary + Monthly chart */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Status summary donut */}
        <div className="rounded-lg border bg-white p-5 shadow-sm">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Current Status
          </h3>
          <StatusDonut summary={trends.status_summary} />
        </div>

        {/* Monthly completions bar chart */}
        {hasCompletions && (
          <div className="rounded-lg border bg-white p-5 shadow-sm">
            <h3 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
              Items Completed by Month
            </h3>
            <BarChart data={trends.monthly_completions} />
          </div>
        )}
      </div>

      {/* Diagnostic reports frequency chart */}
      {hasDiagnostics && (
        <div className="rounded-lg border bg-white p-5 shadow-sm">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Diagnostic Reports by Month
          </h3>
          <BarChart data={diagnosticBarData} barColorClass="fill-purple-500" />
        </div>
      )}

      {/* Vaccine trend metrics */}
      {hasVaccineMetrics && (
        <div className="rounded-lg border bg-white p-5 shadow-sm">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Vaccinations by Month
          </h3>
          <BarChart data={vaccineBarData} barColorClass="fill-emerald-500" />
          <div className="mt-4 grid gap-2 text-xs text-gray-600 md:grid-cols-2">
            {trends.vaccine_metrics.vaccine_timeline.slice(0, 6).map((v, idx) => (
              <div key={`${v.vaccine_name}-${v.last_done_date}-${idx}`} className="rounded border bg-emerald-50/40 px-3 py-2">
                <div className="font-medium text-gray-700">{v.vaccine_name}</div>
                <div>Last done: {formatDate(v.last_done_date)}</div>
                <div>Next due: {v.next_due_date ? formatDate(v.next_due_date) : "—"}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Activity timeline */}
      {hasTimeline && (
        <div className="rounded-lg border bg-white shadow-sm">
          <div className="border-b bg-gray-50 px-4 py-3">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
              Recent Activity
            </h3>
          </div>
          <div className="divide-y">
            {trends.item_timeline.slice(0, 10).map((item, idx) => (
              <div
                key={`${item.item_name}-${item.last_done_date}-${idx}`}
                className="flex items-center justify-between px-4 py-3"
              >
                <div className="flex flex-col">
                  <span className="text-sm font-medium">{item.item_name}</span>
                  <span className="text-xs text-gray-400">
                    {item.category === "essential" ? "Mandatory" : "Recommended"}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-gray-600">
                    {formatDate(item.last_done_date)}
                  </span>
                  <span
                    className={`inline-block rounded-full px-2 py-0.5 text-[10px] font-medium ${statusClass(item.status)}`}
                  >
                    {statusLabel(item.status)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
