"use client";

import { useEffect, useState } from "react";
import type { AdminUser } from "@/lib/api";
import { adminApi } from "@/lib/api";

export default function UsersPanel({ adminKey }: { adminKey: string }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      setUsers(await adminApi.getUsers(adminKey));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [adminKey]);

  async function handleDelete(userId: string) {
    if (!confirm("Soft-delete this user? This preserves their data.")) return;
    try {
      await adminApi.softDeleteUser(adminKey, userId);
      load();
    } catch (e: any) {
      alert(e.message);
    }
  }

  if (loading)
    return <p className="py-8 text-center text-gray-500">Loading users...</p>;
  if (error)
    return <p className="py-8 text-center text-red-600">{error}</p>;

  return (
    <div className="overflow-x-auto rounded-lg border bg-white shadow-sm">
      <table className="w-full text-left text-sm">
        <thead className="border-b bg-gray-50 text-xs uppercase text-gray-500">
          <tr>
            <th className="px-4 py-3">Name</th>
            <th className="px-4 py-3">Mobile</th>
            <th className="px-4 py-3">Pincode</th>
            <th className="px-4 py-3">Consent</th>
            <th className="px-4 py-3">State</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Created</th>
            <th className="px-4 py-3">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {users.map((u) => (
            <tr key={u.id} className="hover:bg-gray-50">
              <td className="px-4 py-3 font-medium">
                {u.full_name || "—"}
              </td>
              <td className="px-4 py-3">{u.mobile_number}</td>
              <td className="px-4 py-3">{u.pincode || "—"}</td>
              <td className="px-4 py-3">
                {u.consent_given ? (
                  <span className="text-green-600">Yes</span>
                ) : (
                  <span className="text-gray-400">No</span>
                )}
              </td>
              <td className="px-4 py-3 capitalize">{u.onboarding_state}</td>
              <td className="px-4 py-3">
                {u.is_deleted ? (
                  <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700">
                    Deleted
                  </span>
                ) : (
                  <span className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-700">
                    Active
                  </span>
                )}
              </td>
              <td className="px-4 py-3 text-gray-500">
                {u.created_at.slice(0, 10)}
              </td>
              <td className="px-4 py-3">
                {!u.is_deleted && (
                  <button
                    onClick={() => handleDelete(u.id)}
                    className="text-xs text-red-600 hover:underline"
                  >
                    Delete
                  </button>
                )}
              </td>
            </tr>
          ))}
          {users.length === 0 && (
            <tr>
              <td colSpan={8} className="px-4 py-8 text-center text-gray-400">
                No users found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
