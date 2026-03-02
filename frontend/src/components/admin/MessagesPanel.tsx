"use client";

import { useEffect, useState } from "react";
import type { AdminMessage } from "@/lib/api";
import { adminApi } from "@/lib/api";

export default function MessagesPanel({ adminKey }: { adminKey: string }) {
  const [messages, setMessages] = useState<AdminMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"all" | "incoming" | "outgoing">("all");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const direction = filter === "all" ? undefined : filter;
      setMessages(await adminApi.getMessages(adminKey, direction, 200));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [adminKey, filter]);

  return (
    <div>
      {/* Filter */}
      <div className="mb-4 flex gap-2">
        {(["all", "incoming", "outgoing"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded px-3 py-1 text-sm capitalize ${
              filter === f
                ? "bg-blue-600 text-white"
                : "bg-white text-gray-600 border hover:bg-gray-50"
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {loading ? (
        <p className="py-8 text-center text-gray-500">Loading messages...</p>
      ) : error ? (
        <p className="py-8 text-center text-red-600">{error}</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="border-b bg-gray-50 text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-3">Direction</th>
                <th className="px-4 py-3">Mobile</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Payload</th>
                <th className="px-4 py-3">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {messages.map((m) => (
                <tr key={m.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
                        m.direction === "incoming"
                          ? "bg-blue-100 text-blue-800"
                          : "bg-gray-100 text-gray-700"
                      }`}
                    >
                      {m.direction}
                    </span>
                  </td>
                  <td className="px-4 py-3">{m.mobile_number}</td>
                  <td className="px-4 py-3">{m.message_type}</td>
                  <td className="max-w-md truncate px-4 py-3 text-gray-500">
                    {m.payload}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-gray-500">
                    {m.created_at}
                  </td>
                </tr>
              ))}
              {messages.length === 0 && (
                <tr>
                  <td
                    colSpan={5}
                    className="px-4 py-8 text-center text-gray-400"
                  >
                    No messages found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
