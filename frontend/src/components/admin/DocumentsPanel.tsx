"use client";

import { useEffect, useState } from "react";
import type { AdminDocument } from "@/lib/api";
import { adminApi } from "@/lib/api";

interface PetGroup {
  pet_id: string;
  pet_name: string;
  docs: AdminDocument[];
  failedCount: number;
}

function groupByPet(docs: AdminDocument[]): PetGroup[] {
  const map = new Map<string, PetGroup>();
  for (const d of docs) {
    let group = map.get(d.pet_id);
    if (!group) {
      group = { pet_id: d.pet_id, pet_name: d.pet_name, docs: [], failedCount: 0 };
      map.set(d.pet_id, group);
    }
    group.docs.push(d);
    if (d.extraction_status === "failed") group.failedCount++;
  }
  return Array.from(map.values());
}

function extractionBadge(status: string) {
  const map: Record<string, string> = {
    success: "bg-green-100 text-green-800",
    pending: "bg-yellow-100 text-yellow-800",
    failed: "bg-red-100 text-red-800",
  };
  return map[status] || "bg-gray-100 text-gray-600";
}

export default function DocumentsPanel({ adminKey }: { adminKey: string }) {
  const [docs, setDocs] = useState<AdminDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  useEffect(() => {
    setLoading(true);
    setError("");
    adminApi
      .getDocuments(adminKey)
      .then(setDocs)
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false));
  }, [adminKey]);

  if (loading)
    return <p className="py-8 text-center text-gray-500">Loading documents...</p>;
  if (error)
    return <p className="py-8 text-center text-red-600">{error}</p>;

  const groups = groupByPet(docs);

  function togglePet(petId: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(petId)) next.delete(petId);
      else next.add(petId);
      return next;
    });
  }

  return (
    <div className="space-y-4">
      {/* Summary */}
      <p className="text-sm text-gray-500">
        {docs.length} document{docs.length !== 1 ? "s" : ""} across {groups.length} pet{groups.length !== 1 ? "s" : ""}
      </p>

      {groups.length === 0 && (
        <p className="py-8 text-center text-gray-400">No documents found.</p>
      )}

      {groups.map((g) => {
        const isCollapsed = collapsed.has(g.pet_id);
        return (
          <div key={g.pet_id} className="overflow-hidden rounded-lg border bg-white shadow-sm">
            {/* Pet header — clickable */}
            <button
              onClick={() => togglePet(g.pet_id)}
              className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-gray-50"
            >
              <span
                className={`inline-block text-xs transition-transform ${isCollapsed ? "" : "rotate-90"}`}
              >
                ▶
              </span>
              <span className="font-medium">{g.pet_name}</span>
              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                {g.docs.length}
              </span>
              {g.failedCount > 0 && (
                <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                  {g.failedCount} failed
                </span>
              )}
            </button>

            {/* Documents table — shown when expanded */}
            {!isCollapsed && (
              <table className="w-full table-fixed text-left text-xs sm:text-sm">
                <thead className="border-t bg-gray-50 text-xs uppercase text-gray-500">
                  <tr>
                    <th className="w-1/2 px-2 py-2 sm:px-4">Document</th>
                    <th className="w-1/4 px-2 py-2 sm:px-4">Extraction</th>
                    <th className="w-1/4 px-2 py-2 sm:px-4">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {g.docs.map((d) => (
                    <tr key={d.id} className="hover:bg-gray-50">
                      <td className="break-words px-2 py-2 sm:px-4">{d.document_name}</td>
                      <td className="px-2 py-2 sm:px-4">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${extractionBadge(d.extraction_status)}`}
                        >
                          {d.extraction_status}
                        </span>
                      </td>
                      <td className="px-2 py-2 text-gray-500 sm:px-4">{d.created_at.slice(0, 10)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        );
      })}
    </div>
  );
}
