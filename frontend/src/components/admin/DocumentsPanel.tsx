"use client";

import { useEffect, useState } from "react";
import type { AdminDocument } from "@/lib/api";
import { adminApi } from "@/lib/api";

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

  async function load() {
    setLoading(true);
    setError("");
    try {
      setDocs(await adminApi.getDocuments(adminKey));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [adminKey]);

  if (loading)
    return (
      <p className="py-8 text-center text-gray-500">Loading documents...</p>
    );
  if (error)
    return <p className="py-8 text-center text-red-600">{error}</p>;

  return (
    <div className="overflow-x-auto rounded-lg border bg-white shadow-sm">
      <table className="w-full text-left text-sm">
        <thead className="border-b bg-gray-50 text-xs uppercase text-gray-500">
          <tr>
            <th className="px-4 py-3">Pet</th>
            <th className="px-4 py-3">Document</th>
            <th className="px-4 py-3">Extraction</th>
            <th className="px-4 py-3">Created</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {docs.map((d) => (
            <tr key={d.id} className="hover:bg-gray-50">
              <td className="px-4 py-3 font-medium">{d.pet_name}</td>
              <td className="max-w-xs truncate px-4 py-3">{d.document_name}</td>
              <td className="px-4 py-3">
                <span
                  className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${extractionBadge(d.extraction_status)}`}
                >
                  {d.extraction_status}
                </span>
              </td>
              <td className="px-4 py-3 text-gray-500">
                {d.created_at.slice(0, 10)}
              </td>
            </tr>
          ))}
          {docs.length === 0 && (
            <tr>
              <td colSpan={4} className="px-4 py-8 text-center text-gray-400">
                No documents found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
