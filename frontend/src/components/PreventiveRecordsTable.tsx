"use client";

import { useState } from "react";
import type { PreventiveRecord } from "@/lib/api";
import { updatePreventiveDate } from "@/lib/api";

function statusBadge(status: string) {
  const map: Record<string, string> = {
    up_to_date: "bg-green-100 text-green-800",
    upcoming: "bg-yellow-100 text-yellow-800",
    overdue: "bg-red-100 text-red-800",
    cancelled: "bg-gray-100 text-gray-500",
  };
  return map[status] || "bg-gray-100 text-gray-600";
}

interface Props {
  records: PreventiveRecord[];
  token: string;
  onUpdated: () => void;
}

export default function PreventiveRecordsTable({
  records,
  token,
  onUpdated,
}: Props) {
  const [editingItem, setEditingItem] = useState<string | null>(null);
  const [dateInput, setDateInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSave(itemName: string) {
    if (!dateInput.trim()) {
      setError("Please enter a date.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await updatePreventiveDate(token, itemName, dateInput.trim());
      setEditingItem(null);
      setDateInput("");
      onUpdated();
    } catch (e: any) {
      setError(e.message || "Failed to update date.");
    } finally {
      setSaving(false);
    }
  }

  if (records.length === 0) {
    return (
      <div className="rounded-lg border bg-white p-6 text-center text-gray-400">
        No preventive records yet.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border bg-white shadow-sm">
      <table className="w-full text-left text-sm">
        <thead className="border-b bg-gray-50 text-xs uppercase text-gray-500">
          <tr>
            <th className="px-4 py-3">Item</th>
            <th className="px-4 py-3">Category</th>
            <th className="px-4 py-3">Last Done</th>
            <th className="px-4 py-3">Next Due</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Recurrence</th>
            <th className="px-4 py-3">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {records.map((r) => (
            <tr key={r.item_name} className="hover:bg-gray-50">
              <td className="px-4 py-3 font-medium">{r.item_name}</td>
              <td className="px-4 py-3 capitalize">{r.category}</td>
              <td className="px-4 py-3">
                {editingItem === r.item_name ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      placeholder="DD/MM/YYYY"
                      value={dateInput}
                      onChange={(e) => setDateInput(e.target.value)}
                      className="w-32 rounded border px-2 py-1 text-sm"
                      disabled={saving}
                    />
                    <button
                      onClick={() => handleSave(r.item_name)}
                      disabled={saving}
                      className="rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
                    >
                      {saving ? "..." : "Save"}
                    </button>
                    <button
                      onClick={() => {
                        setEditingItem(null);
                        setError("");
                      }}
                      className="text-xs text-gray-500 hover:text-gray-700"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  r.last_done_date || "—"
                )}
              </td>
              <td className="px-4 py-3">{r.next_due_date || "—"}</td>
              <td className="px-4 py-3">
                <span
                  className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${statusBadge(r.status)}`}
                >
                  {r.status.replace(/_/g, " ")}
                </span>
              </td>
              <td className="px-4 py-3 text-gray-500">
                {r.recurrence_days}d
              </td>
              <td className="px-4 py-3">
                {r.status !== "cancelled" && editingItem !== r.item_name && (
                  <button
                    onClick={() => {
                      setEditingItem(r.item_name);
                      setDateInput(r.last_done_date || "");
                      setError("");
                    }}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    Update date
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {error && <p className="px-4 py-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}
