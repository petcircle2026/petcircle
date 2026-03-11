"use client";

import { useEffect, useState } from "react";
import { MEDICINES_STORAGE_PREFIX } from "@/lib/branding";

interface MedicineItem {
  id: string;
  name: string;
  notes: string;
}

export default function MedicinesSection({ token }: { token: string }) {
  const [items, setItems] = useState<MedicineItem[]>([]);
  const [name, setName] = useState("");
  const [notes, setNotes] = useState("");

  const key = `${MEDICINES_STORAGE_PREFIX}${token}`;

  useEffect(() => {
    const raw = localStorage.getItem(key);
    if (raw) setItems(JSON.parse(raw));
  }, [key]);

  useEffect(() => {
    localStorage.setItem(key, JSON.stringify(items));
  }, [items, key]);

  return (
    <div className="rounded-lg border bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">Medicines</h3>
      <div className="mb-3 grid gap-2 md:grid-cols-[1fr_1fr_auto]">
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Medicine name" className="rounded border px-2 py-1 text-sm" />
        <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes / dosage" className="rounded border px-2 py-1 text-sm" />
        <button
          onClick={() => {
            if (!name.trim()) return;
            setItems((prev) => [{ id: crypto.randomUUID(), name: name.trim(), notes: notes.trim() }, ...prev]);
            setName("");
            setNotes("");
          }}
          className="rounded bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700"
        >
          Add
        </button>
      </div>
      <div className="space-y-2">
        {items.length === 0 && <p className="text-sm text-gray-400">No medicines added yet.</p>}
        {items.map((m) => (
          <div key={m.id} className="flex items-center justify-between rounded border px-3 py-2">
            <div>
              <p className="text-sm font-medium">{m.name}</p>
              {m.notes && <p className="text-xs text-gray-500">{m.notes}</p>}
            </div>
            <button className="text-xs text-red-600 hover:underline" onClick={() => setItems((prev) => prev.filter((x) => x.id !== m.id))}>
              Remove
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
