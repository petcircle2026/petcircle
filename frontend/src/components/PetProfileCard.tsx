"use client";

import { useState } from "react";
import type { PetProfile, OwnerInfo } from "@/lib/api";
import { updateWeight } from "@/lib/api";

interface Props {
  pet: PetProfile;
  owner: OwnerInfo;
  token: string;
  onUpdated: () => void;
}

export default function PetProfileCard({ pet, owner, token, onUpdated }: Props) {
  const [editing, setEditing] = useState(false);
  const [weight, setWeight] = useState(String(pet.weight ?? ""));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSave() {
    const val = parseFloat(weight);
    if (isNaN(val) || val <= 0 || val > 999.99) {
      setError("Enter a valid weight (0.01 - 999.99 kg).");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await updateWeight(token, val);
      setEditing(false);
      onUpdated();
    } catch (e: any) {
      setError(e.message || "Failed to update weight.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-blue-100 text-2xl">
          {pet.species === "cat" ? "\uD83D\uDC31" : "\uD83D\uDC36"}
        </div>
        <div>
          <h2 className="text-xl font-bold">{pet.name}</h2>
          {owner.full_name && (
            <p className="text-sm text-gray-500">Owner: {owner.full_name}</p>
          )}
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <dt className="text-gray-500">Species</dt>
        <dd className="capitalize">{pet.species}</dd>

        <dt className="text-gray-500">Breed</dt>
        <dd>{pet.breed || "—"}</dd>

        <dt className="text-gray-500">Gender</dt>
        <dd className="capitalize">{pet.gender || "—"}</dd>

        <dt className="text-gray-500">Date of Birth</dt>
        <dd>{pet.dob || "—"}</dd>

        <dt className="text-gray-500">Neutered</dt>
        <dd>{pet.neutered ? "Yes" : "No"}</dd>

        <dt className="text-gray-500">Weight</dt>
        <dd>
          {editing ? (
            <div className="flex items-center gap-2">
              <input
                type="number"
                step="0.01"
                min="0.01"
                max="999.99"
                value={weight}
                onChange={(e) => setWeight(e.target.value)}
                className="w-24 rounded border px-2 py-1 text-sm"
                disabled={saving}
              />
              <span className="text-gray-400">kg</span>
              <button
                onClick={handleSave}
                disabled={saving}
                className="rounded bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {saving ? "..." : "Save"}
              </button>
              <button
                onClick={() => {
                  setEditing(false);
                  setError("");
                }}
                className="text-xs text-gray-500 hover:text-gray-700"
              >
                Cancel
              </button>
            </div>
          ) : (
            <span>
              {pet.weight ? `${pet.weight} kg` : "—"}{" "}
              <button
                onClick={() => {
                  setWeight(String(pet.weight ?? ""));
                  setEditing(true);
                }}
                className="ml-1 text-xs text-blue-600 hover:underline"
              >
                Edit
              </button>
            </span>
          )}
        </dd>
      </dl>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}
