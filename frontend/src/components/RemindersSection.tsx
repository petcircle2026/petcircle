"use client";

import type { ReminderItem } from "@/lib/api";

function statusDot(status: string) {
  if (status === "sent") return "bg-blue-500";
  if (status === "pending") return "bg-yellow-500";
  return "bg-gray-400";
}

export default function RemindersSection({
  reminders,
}: {
  reminders: ReminderItem[];
}) {
  if (reminders.length === 0) {
    return (
      <div className="rounded-lg border bg-white p-6 text-center text-gray-400">
        No active reminders.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border bg-white shadow-sm">
      <table className="w-full text-left text-sm">
        <thead className="border-b bg-gray-50 text-xs uppercase text-gray-500">
          <tr>
            <th className="px-4 py-3">Item</th>
            <th className="px-4 py-3">Due Date</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Sent At</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {reminders.map((r, i) => (
            <tr key={`${r.item_name}-${i}`} className="hover:bg-gray-50">
              <td className="px-4 py-3 font-medium">{r.item_name}</td>
              <td className="px-4 py-3">{r.next_due_date}</td>
              <td className="px-4 py-3">
                <span className="flex items-center gap-2">
                  <span
                    className={`inline-block h-2 w-2 rounded-full ${statusDot(r.status)}`}
                  />
                  <span className="capitalize">{r.status}</span>
                </span>
              </td>
              <td className="px-4 py-3 text-gray-500">
                {r.sent_at || "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
