"use client";

import { memo, useMemo } from "react";
import type { PreventiveRecord } from "@/lib/api";

/**
 * Apple Watch–style concentric activity rings showing pet care completion
 * across three categories: Health, Nutrition, and Hygiene.
 *
 * Each ring represents the ratio of "up_to_date" items to total non-cancelled
 * items in that circle. A full ring = all items are current.
 *
 * The `circle` field comes directly from the preventive_master table in the
 * backend — no client-side mapping needed.
 */

interface CircleStats {
  done: number;
  total: number;
  percent: number;
}

interface RingsData {
  health: CircleStats;
  nutrition: CircleStats;
  hygiene: CircleStats;
}

function computeRings(records: PreventiveRecord[]): RingsData {
  const buckets: Record<string, { done: number; total: number }> = {
    health: { done: 0, total: 0 },
    nutrition: { done: 0, total: 0 },
    hygiene: { done: 0, total: 0 },
  };

  for (const r of records) {
    if (r.status === "cancelled") continue;
    const circle = r.circle || "health";
    if (!buckets[circle]) continue; // ignore unknown circles
    buckets[circle].total += 1;
    if (r.status === "up_to_date") {
      buckets[circle].done += 1;
    }
  }

  const pct = (d: number, t: number) =>
    t === 0 ? 100 : Math.round((d / t) * 100);

  return {
    health: { ...buckets.health, percent: pct(buckets.health.done, buckets.health.total) },
    nutrition: { ...buckets.nutrition, percent: pct(buckets.nutrition.done, buckets.nutrition.total) },
    hygiene: { ...buckets.hygiene, percent: pct(buckets.hygiene.done, buckets.hygiene.total) },
  };
}

// --- Ring configuration ---
// Outer → inner order: Health, Nutrition, Hygiene
const RINGS = [
  {
    key: "health" as const,
    label: "Health",
    radius: 70,
    strokeWidth: 14,
    color: "#22c55e",     // green-500
    bgColor: "#dcfce7",   // green-100
    icon: "💚",
  },
  {
    key: "nutrition" as const,
    label: "Nutrition",
    radius: 52,
    strokeWidth: 14,
    color: "#3b82f6",     // blue-500
    bgColor: "#dbeafe",   // blue-100
    icon: "🥗",
  },
  {
    key: "hygiene" as const,
    label: "Hygiene",
    radius: 34,
    strokeWidth: 14,
    color: "#a855f7",     // purple-500
    bgColor: "#f3e8ff",   // purple-100
    icon: "✨",
  },
];

interface Props {
  records: PreventiveRecord[];
}

export default memo(function ActivityRings({ records }: Props) {
  const rings = useMemo(() => computeRings(records), [records]);

  return (
    <div className="flex flex-col items-center gap-6">
      {/* Concentric rings SVG */}
      <div className="relative h-48 w-48">
        <svg className="h-full w-full" viewBox="0 0 180 180">
          {RINGS.map((ring) => {
            const data = rings[ring.key];
            const circumference = 2 * Math.PI * ring.radius;
            const offset =
              circumference - (data.percent / 100) * circumference;

            return (
              <g key={ring.key}>
                {/* Background track */}
                <circle
                  cx="90"
                  cy="90"
                  r={ring.radius}
                  fill="none"
                  stroke={ring.bgColor}
                  strokeWidth={ring.strokeWidth}
                />
                {/* Progress arc */}
                <circle
                  cx="90"
                  cy="90"
                  r={ring.radius}
                  fill="none"
                  stroke={ring.color}
                  strokeWidth={ring.strokeWidth}
                  strokeLinecap="round"
                  strokeDasharray={circumference}
                  strokeDashoffset={offset}
                  transform="rotate(-90 90 90)"
                  style={{
                    transition: "stroke-dashoffset 0.8s ease-in-out",
                  }}
                />
                {/* Rounded end cap at start of arc (top center) */}
                {data.percent > 0 && data.percent < 100 && (
                  <circle
                    cx="90"
                    cy={90 - ring.radius}
                    r={ring.strokeWidth / 2 - 0.5}
                    fill={ring.color}
                  />
                )}
              </g>
            );
          })}

          {/* Center icon */}
          <text
            x="90"
            y="90"
            textAnchor="middle"
            dominantBaseline="central"
            fontSize="22"
          >
            🐾
          </text>
        </svg>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap justify-center gap-x-5 gap-y-2">
        {RINGS.map((ring) => {
          const data = rings[ring.key];
          return (
            <div key={ring.key} className="flex items-center gap-2">
              <span
                className="inline-block h-3 w-3 rounded-full"
                style={{ backgroundColor: ring.color }}
              />
              <span className="text-sm text-gray-700">
                {ring.label}
              </span>
              <span className="text-xs font-semibold text-gray-500">
                {data.done}/{data.total}
              </span>
            </div>
          );
        })}
      </div>

      {/* Per-ring detail cards */}
      <div className="grid w-full grid-cols-3 gap-3">
        {RINGS.map((ring) => {
          const data = rings[ring.key];
          return (
            <div
              key={ring.key}
              className="flex flex-col items-center rounded-xl border p-3 text-center"
              style={{ borderColor: ring.bgColor, backgroundColor: `${ring.bgColor}30` }}
            >
              <span className="text-lg">{ring.icon}</span>
              <span
                className="mt-1 text-xl font-bold"
                style={{ color: ring.color }}
              >
                {data.percent}%
              </span>
              <span className="mt-0.5 text-[11px] text-gray-500">
                {ring.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
});
