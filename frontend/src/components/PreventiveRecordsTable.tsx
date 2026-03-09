"use client";

import { useState } from "react";
import type { PreventiveRecord } from "@/lib/api";
import { updatePreventiveDate } from "@/lib/api";

/** Convert YYYY-MM-DD to DD-MM-YYYY for display. */
function formatDate(d: string | null): string {
  if (!d) return "—";
  const parts = d.split("-");
  if (parts.length === 3) return `${parts[2]}-${parts[1]}-${parts[0]}`;
  return d;
}

/** Derive display status: records with no dates are "incomplete". */
function getDisplayStatus(r: PreventiveRecord): string {
  if (
    r.status !== "cancelled" &&
    !r.last_done_date &&
    !r.next_due_date
  ) {
    return "incomplete";
  }
  return r.status;
}

/** Status badge styling. */
function statusBadge(status: string): string {
  const map: Record<string, string> = {
    up_to_date: "bg-green-100 text-green-800",
    upcoming: "bg-yellow-100 text-yellow-800",
    overdue: "bg-red-100 text-red-800",
    incomplete: "bg-orange-100 text-orange-700",
    cancelled: "bg-gray-100 text-gray-500",
  };
  return map[status] || "bg-gray-100 text-gray-600";
}

/** Format status text for display. */
function statusLabel(status: string): string {
  const map: Record<string, string> = {
    up_to_date: "Up To Date",
    upcoming: "Upcoming",
    overdue: "Overdue",
    incomplete: "Incomplete",
    cancelled: "Cancelled",
  };
  return map[status] || status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Priority badge styling (small, inline with item name). */
function priorityBadge(category: string): { label: string; className: string } {
  if (category === "essential") {
    return { label: "Mandatory", className: "bg-red-100 text-red-700" };
  }
  return { label: "Recommended", className: "bg-purple-100 text-purple-700" };
}

/** Sort order for statuses. */
const STATUS_SORT_ORDER: Record<string, number> = {
  overdue: 0,
  upcoming: 1,
  up_to_date: 2,
  incomplete: 3,
  cancelled: 4,
};

/** Sort records by status priority, then by next_due_date within each group. */
function sortRecords(records: PreventiveRecord[]): (PreventiveRecord & { displayStatus: string })[] {
  return records
    .map((r) => ({ ...r, displayStatus: getDisplayStatus(r) }))
    .sort((a, b) => {
      const orderA = STATUS_SORT_ORDER[a.displayStatus] ?? 99;
      const orderB = STATUS_SORT_ORDER[b.displayStatus] ?? 99;
      if (orderA !== orderB) return orderA - orderB;
      // Within same status group, sort by next_due_date ascending (nulls last).
      if (a.next_due_date && b.next_due_date) return a.next_due_date.localeCompare(b.next_due_date);
      if (a.next_due_date) return -1;
      if (b.next_due_date) return 1;
      return 0;
    });
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

    // Client-side future date check.
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const parts = dateInput.trim().split(/[\/\-\.]/);
    if (parts.length === 3) {
      let checkDate: Date | null = null;
      // Try DD/MM/YYYY or DD-MM-YYYY
      if (parts[0].length <= 2 && parts[2].length === 4) {
        checkDate = new Date(parseInt(parts[2]), parseInt(parts[1]) - 1, parseInt(parts[0]));
      }
      // Try YYYY-MM-DD
      else if (parts[0].length === 4) {
        checkDate = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
      }
      if (checkDate && checkDate > today) {
        setError("Last done date cannot be in the future.");
        return;
      }
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

  const sorted = sortRecords(records);

  return (
    <div className="overflow-x-auto rounded-lg border bg-white shadow-sm">
      <table className="w-full text-left text-sm">
        <thead className="border-b bg-gray-50 text-xs uppercase text-gray-500">
          <tr>
            <th className="px-4 py-3">Item</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Next Due</th>
            <th className="px-4 py-3">Last Done</th>
            {/* Recurrence — hidden on mobile */}
            <th className="hidden px-4 py-3 md:table-cell">Recurrence</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {sorted.map((r) => {
            const priority = priorityBadge(r.category);
            const isEditing = editingItem === r.item_name;

            return (
              <tr key={r.item_name} className="hover:bg-gray-50">
                {/* Item + Priority badge inline */}
                <td className="px-4 py-3">
                  <div className="flex flex-col gap-1">
                    <span className="font-medium">{r.item_name}</span>
                    <span
                      className={`inline-block w-fit rounded-full px-2 py-0.5 text-[10px] font-medium ${priority.className}`}
                    >
                      {priority.label}
                    </span>
                  </div>
                </td>

                {/* Status */}
                <td className="px-4 py-3">
                  <span
                    className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${statusBadge(r.displayStatus)}`}
                  >
                    {statusLabel(r.displayStatus)}
                  </span>
                </td>

                {/* Next Due */}
                <td className="px-4 py-3">{formatDate(r.next_due_date)}</td>

                {/* Last Done — click to edit */}
                <td className="px-4 py-3">
                  {isEditing ? (
                    <div className="flex flex-col gap-1.5">
                      <input
                        type="date"
                        value={dateInput}
                        max={new Date().toISOString().split("T")[0]}
                        onChange={(e) => setDateInput(e.target.value)}
                        className="w-36 rounded border px-2 py-1 text-sm"
                        disabled={saving}
                      />
                      <div className="flex items-center gap-2">
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
                    </div>
                  ) : (
                    <button
                      onClick={() => {
                        if (r.displayStatus !== "cancelled") {
                          setEditingItem(r.item_name);
                          // Pre-fill with existing date in YYYY-MM-DD for the date input.
                          setDateInput(r.last_done_date || "");
                          setError("");
                        }
                      }}
                      disabled={r.displayStatus === "cancelled"}
                      className={`text-left ${
                        r.displayStatus === "cancelled"
                          ? "cursor-default text-gray-400"
                          : "cursor-pointer text-blue-600 hover:underline"
                      }`}
                      title={r.displayStatus === "cancelled" ? undefined : "Click to update"}
                    >
                      {formatDate(r.last_done_date)}
                    </button>
                  )}
                </td>

                {/* Recurrence — hidden on mobile */}
                <td className="hidden px-4 py-3 text-gray-500 md:table-cell">
                  {r.recurrence_days} days
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {error && <p className="px-4 py-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}
