"use client";

import { useCallback, useEffect, useState } from "react";
import type { DashboardData } from "@/lib/api";
import { fetchDashboard } from "@/lib/api";
import PetProfileCard from "./PetProfileCard";
import HealthScoreRing from "./HealthScoreRing";
import PreventiveRecordsTable from "./PreventiveRecordsTable";
import RemindersSection from "./RemindersSection";
import DocumentsSection from "./DocumentsSection";

export default function DashboardClient({ token }: { token: string }) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const d = await fetchDashboard(token);
      setData(d);
    } catch (e: any) {
      setError(e.message || "Failed to load dashboard.");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600" />
          <p className="text-gray-500">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center p-8">
        <div className="max-w-md rounded-lg border border-red-200 bg-red-50 p-8 text-center">
          <h2 className="mb-2 text-lg font-semibold text-red-800">
            Unable to load dashboard
          </h2>
          <p className="text-sm text-red-600">{error}</p>
        </div>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="mx-auto max-w-5xl space-y-8 p-4 sm:p-8">
      {/* Header */}
      <header className="text-center">
        <h1 className="text-2xl font-bold sm:text-3xl">
          {data.pet.name}&apos;s Health Dashboard
        </h1>
        {data.owner.full_name && (
          <p className="mt-1 text-gray-500">
            Managed by {data.owner.full_name}
          </p>
        )}
      </header>

      {/* Top: Profile + Health Score */}
      <div className="grid gap-6 md:grid-cols-2">
        <PetProfileCard
          pet={data.pet}
          owner={data.owner}
          token={token}
          onUpdated={load}
        />
        <div className="flex flex-col items-center justify-center rounded-lg border bg-white p-6 shadow-sm">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Health Score
          </h3>
          <HealthScoreRing data={data.health_score} />
        </div>
      </div>

      {/* Preventive Records */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">Preventive Records</h2>
        <PreventiveRecordsTable
          records={data.preventive_records}
          token={token}
          onUpdated={load}
        />
      </section>

      {/* Reminders */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">Active Reminders</h2>
        <RemindersSection reminders={data.reminders} />
      </section>

      {/* Documents */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">Uploaded Documents</h2>
        <DocumentsSection documents={data.documents} />
      </section>

      {/* Footer */}
      <footer className="py-4 text-center text-xs text-gray-400">
        PetCircle — Preventive Pet Health System
      </footer>
    </div>
  );
}
