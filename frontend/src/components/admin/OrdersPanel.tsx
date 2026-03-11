"use client";

import { useEffect, useState } from "react";
import type { AdminOrder } from "@/lib/api";
import { adminApi } from "@/lib/api";
import { formatPhoneForDisplay } from "@/lib/phone";

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  completed: "bg-green-100 text-green-800",
  cancelled: "bg-red-100 text-red-800",
  confirmed: "bg-blue-100 text-blue-800",
};

const CATEGORY_LABELS: Record<string, string> = {
  medicines: "Medicines",
  food_nutrition: "Food & Nutrition",
  supplements: "Supplements",
};

const STATUS_OPTIONS = ["all", "pending", "completed", "cancelled"];

const STATUS_LABELS: Record<string, string> = {
  all: "All",
  pending: "Pending",
  completed: "Fulfilled",
  cancelled: "Cancelled",
  confirmed: "Confirmed",
};

const CATEGORY_ALIASES: Record<string, string> = {
  medicines: "medicines",
  medicine: "medicines",
  "food & nutrition": "food_nutrition",
  "food and nutrition": "food_nutrition",
  food: "food_nutrition",
  nutrition: "food_nutrition",
  supplements: "supplements",
  supplement: "supplements",
};

function parseOrderItemsByCategory(itemsDescription: string, category: string): string[] {
  const rawItems = itemsDescription
    .split(/\r?\n|,/) 
    .map((item) => item.replace(/^[-*•]\s*/, "").trim())
    .filter(Boolean);

  const categorizedItems: string[] = [];
  const fallbackItems: string[] = [];
  let foundCategoryPrefixes = false;

  for (const item of rawItems) {
    const match = item.match(/^([A-Za-z\s&]+):\s*(.+)$/);
    if (!match) {
      fallbackItems.push(item);
      continue;
    }

    const normalizedPrefix = match[1].trim().toLowerCase();
    const mappedCategory = CATEGORY_ALIASES[normalizedPrefix];
    if (!mappedCategory) {
      fallbackItems.push(item);
      continue;
    }

    foundCategoryPrefixes = true;
    if (mappedCategory === category) {
      categorizedItems.push(match[2].trim());
    }
  }

  if (foundCategoryPrefixes) {
    return categorizedItems.length > 0 ? categorizedItems : [];
  }

  return fallbackItems;
}

export default function OrdersPanel({ adminKey }: { adminKey: string }) {
  const [orders, setOrders] = useState<AdminOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [notesInput, setNotesInput] = useState<Record<string, string>>({});

  async function load(status?: string) {
    setLoading(true);
    setError("");
    try {
      const filterStatus = status === "all" ? undefined : status;
      setOrders(await adminApi.getOrders(adminKey, filterStatus));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(statusFilter);
  }, [adminKey, statusFilter]);

  async function handleStatusChange(orderId: string, newStatus: string) {
    setActionLoading(orderId);
    try {
      const notes = notesInput[orderId] || undefined;
      await adminApi.updateOrderStatus(adminKey, orderId, newStatus, notes);
      setNotesInput((prev) => {
        const next = { ...prev };
        delete next[orderId];
        return next;
      });
      await load(statusFilter);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setActionLoading(null);
    }
  }

  if (loading)
    return <p className="py-8 text-center text-gray-500">Loading orders...</p>;
  if (error)
    return <p className="py-8 text-center text-red-600">{error}</p>;

  return (
    <div>
      {/* Filter */}
      <div className="mb-4 flex items-center gap-3">
        <label className="text-sm font-medium text-gray-600">Status:</label>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded border px-3 py-1.5 text-sm"
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s] || s}
            </option>
          ))}
        </select>
        <span className="text-sm text-gray-400">
          {orders.length} order{orders.length !== 1 ? "s" : ""}
        </span>
      </div>

      {orders.length === 0 ? (
        <p className="py-8 text-center text-gray-400">No orders found.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full text-left text-sm">
            <thead className="bg-gray-50 text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-3">Date</th>
                <th className="px-4 py-3">User</th>
                <th className="px-4 py-3">Pet</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Items</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Notes</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {orders.map((o) => {
                const orderItems = parseOrderItemsByCategory(o.items_description, o.category);

                return (
                  <tr key={o.id} className="hover:bg-gray-50">
                    <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                      {new Date(o.created_at).toLocaleDateString("en-IN", {
                        day: "2-digit",
                        month: "short",
                        year: "numeric",
                      })}
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium">{o.user_name}</div>
                      <div className="text-xs text-gray-400">{formatPhoneForDisplay(o.user_phone)}</div>
                    </td>
                    <td className="px-4 py-3">{o.pet_name || "-"}</td>
                    <td className="px-4 py-3">
                      {CATEGORY_LABELS[o.category] || o.category}
                    </td>
                    <td className="max-w-xs px-4 py-3">
                      {orderItems.length > 0 ? (
                        <ul className="space-y-1">
                          {orderItems.map((item, idx) => (
                            <li key={`${o.id}-item-${idx}`} className="break-words text-gray-700">
                              {item}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          STATUS_COLORS[o.status] || "bg-gray-100 text-gray-800"
                        }`}
                      >
                        {STATUS_LABELS[o.status] || o.status}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <input
                        type="text"
                        placeholder={o.admin_notes || "Add notes..."}
                        value={notesInput[o.id] ?? ""}
                        onChange={(e) =>
                          setNotesInput((prev) => ({
                            ...prev,
                            [o.id]: e.target.value,
                          }))
                        }
                        className="w-32 rounded border px-2 py-1 text-xs"
                      />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1">
                        {o.status === "pending" && (
                          <button
                            onClick={() => handleStatusChange(o.id, "completed")}
                            disabled={actionLoading === o.id}
                            className="rounded bg-green-500 px-2 py-1 text-xs text-white hover:bg-green-600 disabled:opacity-50"
                          >
                            Fulfilled
                          </button>
                        )}
                        {o.status === "pending" && (
                          <button
                            onClick={() => handleStatusChange(o.id, "cancelled")}
                            disabled={actionLoading === o.id}
                            className="rounded bg-red-500 px-2 py-1 text-xs text-white hover:bg-red-600 disabled:opacity-50"
                          >
                            Cancelled
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
