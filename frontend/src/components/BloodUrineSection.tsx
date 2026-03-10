"use client";

import type { DocumentItem } from "@/lib/api";

function monthKey(d: string | null): string {
  if (!d) return "Unknown";
  const [y, m] = d.split(" ")[0].split("-");
  return y && m ? `${y}-${m}` : "Unknown";
}

export default function BloodUrineSection({ documents }: { documents: DocumentItem[] }) {
  const relevant = documents.filter((d) => {
    const n = (d.document_name || "").toLowerCase();
    return n.includes("blood") || n.includes("urine") || n.includes("urinalysis");
  });

  const trends: Record<string, number> = {};
  for (const d of relevant) {
    const k = monthKey(d.uploaded_at);
    trends[k] = (trends[k] || 0) + 1;
  }
  const trendRows = Object.entries(trends).sort((a, b) => a[0].localeCompare(b[0]));

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">Blood & Urine Tracking</h3>
      {relevant.length === 0 ? (
        <p className="text-sm text-gray-400">No blood/urine reports found yet.</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <p className="mb-1 text-xs font-semibold text-gray-500">Reports</p>
            <div className="space-y-1 text-sm">
              {relevant.map((d) => (
                <div key={d.id} className="rounded border px-2 py-1">
                  {d.document_name || "Diagnostic report"}
                </div>
              ))}
            </div>
          </div>
          <div>
            <p className="mb-1 text-xs font-semibold text-gray-500">Trend by month</p>
            <div className="space-y-1 text-sm">
              {trendRows.map(([m, c]) => (
                <div key={m} className="flex items-center justify-between rounded border px-2 py-1">
                  <span>{m}</span>
                  <span className="font-medium">{c}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
