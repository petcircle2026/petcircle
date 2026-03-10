"use client";

import type { DiagnosticResultItem } from "@/lib/api";

const PREFERRED_DIRECTION: Record<string, "higher" | "lower"> = {
  hemoglobin: "higher",
  hgb: "higher",
  rbc: "higher",
  platelet: "higher",
  platelets: "higher",
  wbc: "lower",
  creatinine: "lower",
  bun: "lower",
  protein: "lower",
  "urine ph": "lower",
};

function testLabel(t: "blood" | "urine") {
  return t === "blood" ? "CBC dashboard" : "Urine dashboard";
}

function displayValue(r: DiagnosticResultItem): string {
  if (r.value_numeric !== null) return `${r.value_numeric}${r.unit ? ` ${r.unit}` : ""}`;
  return r.value_text || "-";
}

function monthKey(dateStr: string | null): string {
  if (!dateStr) return "Unknown";
  const [y, m] = dateStr.split("-");
  return y && m ? `${y}-${m}` : "Unknown";
}

function trendText(rows: DiagnosticResultItem[]): string {
  if (rows.length < 2) return "Need at least 2 months of data";

  const byMonth = new Map<string, DiagnosticResultItem>();
  for (const r of rows) {
    const key = monthKey(r.observed_at || r.created_at);
    if (!byMonth.has(key)) byMonth.set(key, r);
  }
  const monthly = Array.from(byMonth.entries()).sort((a, b) => a[0].localeCompare(b[0])).map(([, v]) => v);
  if (monthly.length < 2) return "Need at least 2 months of data";

  const first = monthly[0];
  const last = monthly[monthly.length - 1];

  if (last.status_flag && first.status_flag) {
    const score = (s: string | null) => ({ low: 1, high: 1, abnormal: 0, normal: 2 }[s || ""] ?? 1);
    if (score(last.status_flag) > score(first.status_flag)) return "Getting better month-on-month";
    if (score(last.status_flag) < score(first.status_flag)) return "Getting worse month-on-month";
    return "Stable";
  }

  if (first.value_numeric === null || last.value_numeric === null) return "Trend unavailable";
  const key = first.parameter_name.toLowerCase();
  const preferred = Object.entries(PREFERRED_DIRECTION).find(([k]) => key.includes(k))?.[1] || "lower";
  if (Math.abs(last.value_numeric - first.value_numeric) < 0.0001) return "Stable";
  const better = preferred === "higher" ? last.value_numeric > first.value_numeric : last.value_numeric < first.value_numeric;
  return better ? "Getting better month-on-month" : "Getting worse month-on-month";
}

export default function BloodUrineSection({ diagnosticResults }: { diagnosticResults: DiagnosticResultItem[] }) {
  const grouped = {
    blood: diagnosticResults.filter((r) => r.test_type === "blood"),
    urine: diagnosticResults.filter((r) => r.test_type === "urine"),
  };

  function render(type: "blood" | "urine") {
    const rows = grouped[type];
    if (rows.length === 0) return <p className="text-sm text-gray-400">No {type} values found yet.</p>;

    const byParam = rows.reduce<Record<string, DiagnosticResultItem[]>>((acc, row) => {
      acc[row.parameter_name] = acc[row.parameter_name] || [];
      acc[row.parameter_name].push(row);
      return acc;
    }, {});

    return (
      <div className="space-y-3">
        {Object.entries(byParam).map(([param, values]) => {
          const latest = [...values].sort((a, b) => (b.observed_at || b.created_at || "").localeCompare(a.observed_at || a.created_at || ""))[0];
          return (
            <div key={param} className="rounded border p-2">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">{param}</span>
                <span>{displayValue(latest)}</span>
              </div>
              <div className="text-xs text-gray-500">{trendText(values)}</div>
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">Blood & Urine Tracking</h3>
      <div className="grid gap-4 md:grid-cols-2">
        {(["blood", "urine"] as const).map((type) => (
          <div key={type}>
            <p className="mb-2 text-xs font-semibold text-gray-500">{testLabel(type)}</p>
            {render(type)}
          </div>
        ))}
      </div>
    </div>
  );
}
