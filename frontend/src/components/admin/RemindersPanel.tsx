"use client";

import { useEffect, useState } from "react";
import type { AdminReminder } from "@/lib/api";
import { adminApi } from "@/lib/api";

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

  async function load() {
    setLoading(true);
    setError("");
    try {
      setReminders(await adminApi.getReminders(adminKey));
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
      <p className="py-8 text-center text-gray-500">Loading reminders...</p>
    );
  if (error)
    return <p className="py-8 text-center text-red-600">{error}</p>;

  return (
    <div className="overflow-x-auto rounded-lg border bg-white shadow-sm">
      <table className="w-full text-left text-sm">
        <thead className="border-b bg-gray-50 text-xs uppercase text-gray-500">
          <tr>
            <th className="px-4 py-3">Pet</th>
            <th className="px-4 py-3">Item</th>
            <th className="px-4 py-3">Due Date</th>
            <th className="px-4 py-3">Record Status</th>
            <th className="px-4 py-3">Reminder Status</th>
            <th className="px-4 py-3">Sent At</th>
            <th className="px-4 py-3">Created</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {reminders.map((r) => (
            <tr key={r.id} className="hover:bg-gray-50">
              <td className="px-4 py-3 font-medium">{r.pet_name}</td>
              <td className="px-4 py-3">{r.item_name}</td>
              <td className="px-4 py-3">{r.next_due_date}</td>
              <td className="px-4 py-3 capitalize">
                {r.record_status.replace(/_/g, " ")}
              </td>
              <td className="px-4 py-3">
                <span
                  className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${statusBadge(r.reminder_status)}`}
                >
                  {r.reminder_status}
                </span>
              </td>
              <td className="px-4 py-3 text-gray-500">{r.sent_at || "—"}</td>
              <td className="px-4 py-3 text-gray-500">
                {r.created_at.slice(0, 10)}
              </td>
            </tr>
          ))}
          {reminders.length === 0 && (
            <tr>
              <td colSpan={7} className="px-4 py-8 text-center text-gray-400">
                No reminders found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
