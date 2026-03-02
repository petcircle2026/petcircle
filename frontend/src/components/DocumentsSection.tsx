"use client";

import type { DocumentItem } from "@/lib/api";

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

export default function DocumentsSection({
  documents,
}: {
  documents: DocumentItem[];
}) {
  if (documents.length === 0) {
    return (
      <div className="rounded-lg border bg-white p-6 text-center text-gray-400">
        No documents uploaded yet.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border bg-white shadow-sm">
      <table className="w-full text-left text-sm">
        <thead className="border-b bg-gray-50 text-xs uppercase text-gray-500">
          <tr>
            <th className="px-4 py-3">Type</th>
            <th className="px-4 py-3">Extraction</th>
            <th className="px-4 py-3">Uploaded</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {documents.map((d, i) => (
            <tr key={i} className="hover:bg-gray-50">
              <td className="px-4 py-3">
                <span className="mr-2">{mimeIcon(d.mime_type)}</span>
                {d.mime_type}
              </td>
              <td className="px-4 py-3">
                <span
                  className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${extractionBadge(d.extraction_status)}`}
                >
                  {d.extraction_status}
                </span>
              </td>
              <td className="px-4 py-3 text-gray-500">
                {d.uploaded_at || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
