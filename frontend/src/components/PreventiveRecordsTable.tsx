"use client";

import { useMemo, useState } from "react";
import type { PreventiveRecord } from "@/lib/api";
import { updatePreventiveDate } from "@/lib/api";

function formatDate(d: string | null): string {
  if (!d) return "-";
  const parts = d.split("-");
  if (parts.length === 3) return `${parts[2]}-${parts[1]}-${parts[0]}`;
  return d;
}

function getDisplayStatus(r: PreventiveRecord): string {
  if (r.status !== "cancelled" && !r.last_done_date && !r.next_due_date) return "incomplete";
  return r.status;
}

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

function priorityBadge(category: string): { label: string; className: string } {
  if (category === "essential") return { label: "Mandatory", className: "bg-red-100 text-red-700" };
  return { label: "Recommended", className: "bg-purple-100 text-purple-700" };
}

const STATUS_SORT_ORDER: Record<string, number> = {
  overdue: 0,
  upcoming: 1,
  up_to_date: 2,
  incomplete: 3,
  cancelled: 4,
};

type DisplayRecord = PreventiveRecord & { displayStatus: string };

function sortRecords(records: PreventiveRecord[]): DisplayRecord[] {
  return records
    .map((r) => ({ ...r, displayStatus: getDisplayStatus(r) }))
    .sort((a, b) => {
      const orderA = STATUS_SORT_ORDER[a.displayStatus] ?? 99;
      const orderB = STATUS_SORT_ORDER[b.displayStatus] ?? 99;
      if (orderA !== orderB) return orderA - orderB;
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

const CIRCLE_LABELS: Record<string, string> = {
  hygiene: "Hygiene Circle",
  nutrition: "Nutrition Circle",
  health: "Health Circle",
};

export default function PreventiveRecordsTable({ records, token, onUpdated }: Props) {
  const [editingItem, setEditingItem] = useState<string | null>(null);
  const [dateInput, setDateInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSave(itemName: string) {
    if (!dateInput.trim()) return setError("Please enter a date.");

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const parts = dateInput.trim().split(/[\/\-\.]/);
    if (parts.length === 3) {
      let checkDate: Date | null = null;
      if (parts[0].length <= 2 && parts[2].length === 4) {
        checkDate = new Date(parseInt(parts[2]), parseInt(parts[1]) - 1, parseInt(parts[0]));
      } else if (parts[0].length === 4) {
        checkDate = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
      }
      if (checkDate && checkDate > today) return setError("Last done date cannot be in the future.");
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

  const grouped = useMemo(() => {
    const acc: Record<string, PreventiveRecord[]> = { hygiene: [], nutrition: [], health: [] };
    for (const record of records) {
      const key = (record.circle || "health").toLowerCase();
      if (!acc[key]) acc[key] = [];
      acc[key].push(record);
    }
    return Object.fromEntries(Object.entries(acc).map(([k, v]) => [k, sortRecords(v)])) as Record<string, DisplayRecord[]>;
  }, [records]);

  if (records.length === 0) return <div className="rounded-lg border bg-white p-6 text-center text-gray-400">No preventive records yet.</div>;

  return (
    <div className="space-y-4">
      {Object.entries(grouped)
        .filter(([, rs]) => rs.length > 0)
        .map(([circle, circleRecords]) => (
          <div key={circle} className="overflow-x-auto rounded-lg border bg-white shadow-sm">
            <div className="border-b bg-gray-50 px-4 py-2 text-xs font-semibold uppercase tracking-wide text-gray-500">{CIRCLE_LABELS[circle] || `${circle} Circle`}</div>
            <table className="w-full text-left text-sm">
              <thead className="border-b bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-4 py-3">Item</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Next Due / Last Done</th>
                  <th className="hidden px-4 py-3 md:table-cell">Recurrence</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {circleRecords.map((r) => {
                  const priority = priorityBadge(r.category);
                  const isEditing = editingItem === r.item_name;
                  return (
                    <tr key={r.item_name} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-1">
                          <span className="font-medium">{r.item_name}</span>
                          <span className={`inline-block w-fit rounded-full px-2 py-0.5 text-[10px] font-medium ${priority.className}`}>{priority.label}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${statusBadge(r.displayStatus)}`}>{statusLabel(r.displayStatus)}</span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="text-sm text-gray-700">Next due - {formatDate(r.next_due_date)}</div>
                        {isEditing ? (
                          <div className="mt-1.5 flex flex-col gap-1.5">
                            <input type="date" value={dateInput} max={new Date().toISOString().split("T")[0]} onChange={(e) => setDateInput(e.target.value)} className="w-36 rounded border px-2 py-1 text-sm" disabled={saving} />
                            <div className="flex items-center gap-2">
                              <button onClick={() => handleSave(r.item_name)} disabled={saving} className="rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700 disabled:opacity-50">{saving ? "..." : "Save"}</button>
                              <button onClick={() => { setEditingItem(null); setError(""); }} className="text-xs text-gray-500 hover:text-gray-700">Cancel</button>
                            </div>
                          </div>
                        ) : (
                          <button
                            onClick={() => {
                              if (r.displayStatus !== "cancelled") {
                                setEditingItem(r.item_name);
                                setDateInput(r.last_done_date || "");
                                setError("");
                              }
                            }}
                            disabled={r.displayStatus === "cancelled"}
                            className={r.displayStatus === "cancelled" ? "mt-1 text-gray-400" : "mt-1 text-blue-600 hover:underline"}
                            title={r.displayStatus === "cancelled" ? undefined : "Click to update"}
                          >
                            Last done - {formatDate(r.last_done_date)}
                          </button>
                        )}
                      </td>
                      <td className="hidden px-4 py-3 text-gray-500 md:table-cell">{r.recurrence_days} days</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ))}
      {error && <p className="px-1 text-sm text-red-600">{error}</p>}
    </div>
  );
}
