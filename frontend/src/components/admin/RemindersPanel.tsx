"use client";

import { useEffect, useState } from "react";
import type { AdminReminder } from "@/lib/api";
import { adminApi } from "@/lib/api";

interface PetGroup {
  pet_name: string;
  reminders: AdminReminder[];
  overdueCount: number;
}

function groupByPet(reminders: AdminReminder[]): PetGroup[] {
  const map = new Map<string, PetGroup>();
  for (const r of reminders) {
    let group = map.get(r.pet_name);
    if (!group) {
      group = { pet_name: r.pet_name, reminders: [], overdueCount: 0 };
      map.set(r.pet_name, group);
    }
    group.reminders.push(r);
    if (r.record_status === "overdue") group.overdueCount++;
  }
  return Array.from(map.values());
}

function statusBadge(status: string) {
  const map: Record<string, string> = {
    pending: "bg-yellow-100 text-yellow-800",
    sent: "bg-blue-100 text-blue-800",
    completed: "bg-green-100 text-green-800",
    snoozed: "bg-purple-100 text-purple-800",
  };
  return map[status] || "bg-gray-100 text-gray-600";
}

export default function RemindersPanel({ adminKey }: { adminKey: string }) {
  const [reminders, setReminders] = useState<AdminReminder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  useEffect(() => {
    setLoading(true);
    setError("");
    adminApi
      .getReminders(adminKey)
      .then(setReminders)
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false));
  }, [adminKey]);

  if (loading)
    return <p className="py-8 text-center text-gray-500">Loading reminders...</p>;
  if (error)
    return <p className="py-8 text-center text-red-600">{error}</p>;

  const groups = groupByPet(reminders);

  function togglePet(petName: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(petName)) next.delete(petName);
      else next.add(petName);
      return next;
    });
  }

  return (
    <div className="space-y-4">
      {/* Summary */}
      <p className="text-sm text-gray-500">
        {reminders.length} reminder{reminders.length !== 1 ? "s" : ""} across {groups.length} pet{groups.length !== 1 ? "s" : ""}
      </p>

      {groups.length === 0 && (
        <p className="py-8 text-center text-gray-400">No reminders found.</p>
      )}

      {groups.map((g) => {
        const isCollapsed = collapsed.has(g.pet_name);
        return (
          <div key={g.pet_name} className="overflow-hidden rounded-lg border bg-white shadow-sm">
            {/* Pet header — clickable */}
            <button
              onClick={() => togglePet(g.pet_name)}
              className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-gray-50"
            >
              <span
                className={`inline-block text-xs transition-transform ${isCollapsed ? "" : "rotate-90"}`}
              >
                ▶
              </span>
              <span className="font-medium">{g.pet_name}</span>
              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                {g.reminders.length}
              </span>
              {g.overdueCount > 0 && (
                <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-700">
                  {g.overdueCount} overdue
                </span>
              )}
            </button>

            {/* Reminders table — shown when expanded */}
            {!isCollapsed && (
              <table className="w-full text-left text-sm">
                <thead className="border-t bg-gray-50 text-xs uppercase text-gray-500">
                  <tr>
                    <th className="px-4 py-2">Item</th>
                    <th className="px-4 py-2">Due Date</th>
                    <th className="px-4 py-2">Record Status</th>
                    <th className="px-4 py-2">Reminder Status</th>
                    <th className="px-4 py-2">Sent At</th>
                    <th className="px-4 py-2">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {g.reminders.map((r) => (
                    <tr key={r.id} className="hover:bg-gray-50">
                      <td className="px-4 py-2">{r.item_name}</td>
                      <td className="px-4 py-2">{r.next_due_date}</td>
                      <td className="px-4 py-2 capitalize">
                        {r.record_status.replace(/_/g, " ")}
                      </td>
                      <td className="px-4 py-2">
                        <span
                          className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${statusBadge(r.reminder_status)}`}
                        >
                          {r.reminder_status}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-gray-500">{r.sent_at || "—"}</td>
                      <td className="px-4 py-2 text-gray-500">{r.created_at.slice(0, 10)}</td>
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
