"use client";

import type { HealthScore } from "@/lib/api";

function scoreColor(score: number): string {
  if (score >= 80) return "text-green-500";
  if (score >= 50) return "text-yellow-500";
  return "text-red-500";
}

function ringColor(score: number): string {
  if (score >= 80) return "stroke-green-500";
  if (score >= 50) return "stroke-yellow-500";
  return "stroke-red-500";
}

export default function HealthScoreRing({ data }: { data: HealthScore }) {
  const pct = Math.min(data.score, 100);
  const circumference = 2 * Math.PI * 54;
  const offset = circumference - (pct / 100) * circumference;

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative h-36 w-36">
        <svg className="h-full w-full -rotate-90" viewBox="0 0 120 120">
          <circle
            cx="60"
            cy="60"
            r="54"
            fill="none"
            stroke="currentColor"
            strokeWidth="8"
            className="text-gray-200"
          />
          <circle
            cx="60"
            cy="60"
            r="54"
            fill="none"
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className={ringColor(data.score)}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={`text-3xl font-bold ${scoreColor(data.score)}`}>
            {data.score}
          </span>
          <span className="text-xs text-gray-500">/ 100</span>
        </div>
      </div>
      <div className="flex gap-4 text-sm text-gray-600">
        <span>
          Essential: {data.essential_done}/{data.essential_total}
        </span>
        <span>
          Extra: {data.complementary_done}/{data.complementary_total}
        </span>
      </div>
    </div>
  );
}
