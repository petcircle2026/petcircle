"use client";

import { memo, useEffect, useMemo, useState } from "react";
import type { DocumentItem } from "@/lib/api";
import { retryExtraction } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Category display order and labels. */
const CATEGORY_ORDER = ["Vaccination", "Diagnostic", "Prescription", "Other"] as const;

function inferCategory(doc: DocumentItem): (typeof CATEGORY_ORDER)[number] {
  const rawCategory = (doc.document_category || "").trim();
  if (CATEGORY_ORDER.includes(rawCategory as (typeof CATEGORY_ORDER)[number])) {
    if (rawCategory !== "Other") return rawCategory as (typeof CATEGORY_ORDER)[number];
  }

  const name = `${doc.document_name || ""} ${doc.hospital_name || ""}`.toLowerCase();
  if (/(blood|cbc|urine|urinalysis|hematology|haematology|lab|diagnostic)/.test(name)) {
    return "Diagnostic";
  }
  if (/(prescription|rx|medicine|medication)/.test(name)) {
    return "Prescription";
  }
  if (/(vaccin|rabies|booster|dhpp|fvrcp)/.test(name)) {
    return "Vaccination";
  }
  return "Other";
}

/** Category badge colors. */
function categoryBadge(cat: string | null): string {
  const map: Record<string, string> = {
    Vaccination: "bg-blue-100 text-blue-800",
    Diagnostic: "bg-purple-100 text-purple-800",
    Prescription: "bg-amber-100 text-amber-800",
    Other: "bg-gray-100 text-gray-600",
  };
  return map[cat || "Other"] || "bg-gray-100 text-gray-600";
}

function mimeIcon(mime: string) {
  if (mime === "application/pdf") return "\uD83D\uDCC4";
  if (mime.startsWith("image/")) return "\uD83D\uDDBC\uFE0F";
  return "\uD83D\uDCC1";
}

function extractionBadge(status: string) {
  const map: Record<string, string> = {
    success: "bg-green-100 text-green-800",
    pending: "bg-yellow-100 text-yellow-800",
    failed: "bg-red-100 text-red-800",
  };
  return map[status] || "bg-gray-100 text-gray-600";
}

/** Convert YYYY-MM-DD HH:MM:SS to DD-MM-YYYY for display. */
function formatDate(d: string | null): string {
  if (!d) return "\u2014";
  const datePart = d.split(" ")[0];
  const parts = datePart.split("-");
  if (parts.length === 3 && parts[0].length === 4) {
    return `${parts[2]}-${parts[1]}-${parts[0]}`;
  }
  return d;
}

/** Retry button shown next to failed documents. */
function RetryButton({
  documentId,
  token,
  onRetried,
}: {
  documentId: string;
  token: string;
  onRetried: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleRetry() {
    setLoading(true);
    setError("");
    try {
      await retryExtraction(token, documentId);
      onRetried();
    } catch (e: any) {
      setError(e.message || "Retry failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <span className="inline-flex items-center gap-2">
      <button
        onClick={handleRetry}
        disabled={loading}
        className="rounded bg-red-600 px-2 py-0.5 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
      >
        {loading ? "Retrying..." : "Retry"}
      </button>
      {error && (
        <span className="text-xs text-red-600" title={error}>
          Failed
        </span>
      )}
    </span>
  );
}

/** Document table for a single category. */
function CategoryTable({
  docs,
  token,
  onRefresh,
  onOpen,
}: {
  docs: DocumentItem[];
  token: string;
  onRefresh: () => void;
  onOpen: (doc: DocumentItem) => void;
}) {
  return (
    <table className="w-full text-left text-sm">
      <thead className="border-b bg-gray-50 text-xs uppercase text-gray-500">
        <tr>
          <th className="px-4 py-2">Document</th>
          <th className="px-4 py-2">Extraction</th>
          <th className="px-4 py-2">Uploaded</th>
        </tr>
      </thead>
      <tbody className="divide-y">
        {docs.map((d) => (
          <tr key={d.id} className="hover:bg-gray-50">
            <td className="px-4 py-2.5 font-medium">
              <button
                onClick={() => onOpen(d)}
                className="text-left text-blue-700 hover:underline"
                title="Open document"
              >
                <span className="mr-2">{mimeIcon(d.mime_type)}</span>
                {d.document_name || "Uploaded Document"}
              </button>
            </td>
            <td className="px-4 py-2.5">
              <span
                className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize ${extractionBadge(d.extraction_status)}`}
              >
                {d.extraction_status}
              </span>
              {d.extraction_status === "failed" && (
                <span className="ml-2">
                  <RetryButton
                    documentId={d.id}
                    token={token}
                    onRetried={onRefresh}
                  />
                </span>
              )}
            </td>
            <td className="px-4 py-2.5 text-gray-500">
              {formatDate(d.uploaded_at)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default memo(function DocumentsSection({
  documents,
  token,
  onRefresh,
}: {
  documents: DocumentItem[];
  token: string;
  onRefresh: () => void;
}) {
  const [selectedDoc, setSelectedDoc] = useState<DocumentItem | null>(null);

  useEffect(() => {
    if (!selectedDoc) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedDoc(null);
    };
    window.addEventListener("keydown", onEsc);
    return () => {
      document.body.style.overflow = original;
      window.removeEventListener("keydown", onEsc);
    };
  }, [selectedDoc]);

  if (documents.length === 0) {
    return (
      <div className="rounded-lg border bg-white p-6 text-center text-gray-400">
        No documents uploaded yet.
      </div>
    );
  }

  // Group documents by category, sorted by uploaded_at (most recent first) within each.
  const grouped = useMemo(() => {
    const groups: Record<string, DocumentItem[]> = {};
    for (const cat of CATEGORY_ORDER) {
      groups[cat] = [];
    }

    for (const doc of documents) {
      const cat = inferCategory(doc);
      groups[cat].push(doc);
    }

    // Sort each group by uploaded_at descending.
    for (const cat of CATEGORY_ORDER) {
      groups[cat].sort((a, b) => {
        const ta = a.uploaded_at || "";
        const tb = b.uploaded_at || "";
        return tb.localeCompare(ta);
      });
    }

    return groups;
  }, [documents]);

  // Only show categories that have documents.
  const activeCategories = CATEGORY_ORDER.filter((cat) => grouped[cat].length > 0);

  return (
    <div className="space-y-4">
      {activeCategories.map((cat) => (
        <div key={cat} className="overflow-x-auto rounded-lg border bg-white shadow-sm">
          <div className="flex items-center gap-2 border-b bg-gray-50 px-4 py-3">
            <span
              className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-semibold ${categoryBadge(cat)}`}
            >
              {cat}
            </span>
            <span className="text-xs text-gray-400">
              {grouped[cat].length} document{grouped[cat].length !== 1 ? "s" : ""}
            </span>
          </div>
          <CategoryTable docs={grouped[cat]} token={token} onRefresh={onRefresh} onOpen={setSelectedDoc} />
        </div>
      ))}
    

      {selectedDoc && (
        <div
          className="fixed inset-0 z-[100] bg-black/75 backdrop-blur-sm"
          onClick={() => setSelectedDoc(null)}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="mx-auto flex h-full w-full max-w-6xl flex-col bg-white"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b px-4 py-3">
              <div className="truncate pr-4 text-sm font-medium text-gray-700">
                {selectedDoc.document_name || "Uploaded Document"}
              </div>
              <button
                onClick={() => setSelectedDoc(null)}
                className="rounded border px-3 py-1 text-sm text-gray-700 hover:bg-gray-100"
              >
                Close
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-3">
              {selectedDoc.mime_type === "application/pdf" ? (
                <iframe
                  src={`${API_BASE}/dashboard/${token}/document/${selectedDoc.id}`}
                  className="h-full min-h-[75vh] w-full rounded border"
                  title={selectedDoc.document_name || "Document"}
                />
              ) : (
                <img
                  src={`${API_BASE}/dashboard/${token}/document/${selectedDoc.id}`}
                  alt={selectedDoc.document_name || "Document"}
                  className="h-full max-h-[82vh] w-full rounded border object-contain"
                />
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  );
});
