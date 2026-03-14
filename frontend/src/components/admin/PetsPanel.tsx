"use client";

import { useCallback, useEffect, useState } from "react";
import type { AdminPet } from "@/lib/api";
import { adminApi, getErrorMessage } from "@/lib/api";

export default function PetsPanel({ adminKey }: { adminKey: string }) {
  const [pets, setPets] = useState<AdminPet[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setPets(await adminApi.getPets(adminKey));
    } catch (e: unknown) {
      setError(getErrorMessage(e, "Failed to load pets."));
    } finally {
      setLoading(false);
    }
  }, [adminKey]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleRevokeToken(petId: string) {
    if (!confirm("Revoke this pet's dashboard token?")) return;
    try {
      await adminApi.revokeToken(adminKey, petId);
      alert("Token revoked.");
    } catch (e: unknown) {
      alert(getErrorMessage(e, "Failed to revoke token."));
    }
  }

  async function handleTriggerReminder(petId: string) {
    try {
      await adminApi.triggerReminder(adminKey, petId);
      alert("Reminder triggered.");
    } catch (e: unknown) {
      alert(getErrorMessage(e, "Failed to trigger reminder."));
    }
  }

  if (loading)
    return <p className="py-8 text-center text-gray-500">Loading pets...</p>;
  if (error)
    return <p className="py-8 text-center text-red-600">{error}</p>;

  return (
    <div className="overflow-x-auto rounded-lg border bg-white shadow-sm">
      <table className="w-full text-left text-sm">
        <thead className="border-b bg-gray-50 text-xs uppercase text-gray-500">
          <tr>
            <th className="px-4 py-3">Name</th>
            <th className="px-4 py-3">Species</th>
            <th className="px-4 py-3">Breed</th>
            <th className="px-4 py-3">Gender</th>
            <th className="px-4 py-3">DOB</th>
            <th className="px-4 py-3">Weight</th>
            <th className="px-4 py-3">Neutered</th>
            <th className="px-4 py-3">Status</th>
            <th className="px-4 py-3">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {pets.map((p) => (
            <tr key={p.id} className="hover:bg-gray-50">
              <td className="px-4 py-3 font-medium">{p.name}</td>
              <td className="px-4 py-3 capitalize">{p.species}</td>
              <td className="px-4 py-3">{p.breed || "—"}</td>
              <td className="px-4 py-3 capitalize">{p.gender || "—"}</td>
              <td className="px-4 py-3">{p.dob || "—"}</td>
              <td className="px-4 py-3">
                {p.weight ? `${p.weight} kg` : "—"}
              </td>
              <td className="px-4 py-3">{p.neutered ? "Yes" : "No"}</td>
              <td className="px-4 py-3">
                {p.is_deleted ? (
                  <span className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-700">
                    Deleted
                  </span>
                ) : (
                  <span className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-700">
                    Active
                  </span>
                )}
              </td>
              <td className="px-4 py-3">
                <div className="flex gap-2">
                  <button
                    onClick={() => handleRevokeToken(p.id)}
                    className="text-xs text-red-600 hover:underline"
                  >
                    Revoke token
                  </button>
                  <button
                    onClick={() => handleTriggerReminder(p.id)}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    Trigger reminder
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {pets.length === 0 && (
            <tr>
              <td colSpan={9} className="px-4 py-8 text-center text-gray-400">
                No pets found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
