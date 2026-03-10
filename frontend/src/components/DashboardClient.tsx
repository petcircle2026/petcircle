"use client";

import { useCallback, useEffect, useState } from "react";
import type { DashboardData } from "@/lib/api";
import { fetchDashboard } from "@/lib/api";
import ErrorBoundary from "./ErrorBoundary";
import PetProfileCard from "./PetProfileCard";
import ActivityRings from "./ActivityRings";
import PreventiveRecordsTable from "./PreventiveRecordsTable";
import HealthTrendsSection from "./HealthTrendsSection";
import RemindersSection from "./RemindersSection";
import DocumentsSection from "./DocumentsSection";

function DashboardInner({ token }: { token: string }) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  // True when showing cached data because the API is unreachable.
  const [stale, setStale] = useState(false);
  const [cachedAt, setCachedAt] = useState<string | undefined>();
  const [retryCount, setRetryCount] = useState(0);

  const load = useCallback(async () => {
    try {
      setError("");
      // Only show full loading spinner on first load.
      // On refresh, keep existing data visible and show a subtle indicator.
      setData((prev) => {
        if (prev) {
          setRefreshing(true);
        } else {
          setLoading(true);
        }
        return prev;
      });
      const result = await fetchDashboard(token);
      setData(result.data);
      setStale(result.stale);
      setCachedAt(result.cachedAt);
      if (!result.stale) setRetryCount(0);
    } catch (e: any) {
      setData((prev) => {
        // Only set error if we have no data to show.
        if (!prev) {
          setError(e.message || "Failed to load dashboard.");
        }
        return prev;
      });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [token]);

  // Initial load on mount.
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // Auto-retry every 30s when showing stale data, so the dashboard
  // refreshes automatically once the backend recovers.
  // Stops after 20 retries (~10 min) to avoid polling forever.
  // IMPORTANT: This hook must be called unconditionally (before any returns)
  // to satisfy React's rules of hooks.
  useEffect(() => {
    if (!stale || retryCount >= 20) return;
    const interval = setInterval(() => {
      setRetryCount((c) => c + 1);
      load();
    }, 30000);
    return () => clearInterval(interval);
  }, [stale, retryCount, load]);

  if (loading && !data) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600" />
          <p className="text-gray-500">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="flex min-h-screen items-center justify-center p-8">
        <div className="max-w-md rounded-lg border border-red-200 bg-red-50 p-8 text-center">
          <h2 className="mb-2 text-lg font-semibold text-red-800">
            Unable to load dashboard
          </h2>
          <p className="mb-4 text-sm text-red-600">{error}</p>
          <button
            onClick={load}
            className="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  if (!data) return null;

  // Calculate how old the cached data is for the stale banner.
  const staleMinutes = cachedAt
    ? Math.round((Date.now() - new Date(cachedAt).getTime()) / 60000)
    : null;

  return (
    <div className="mx-auto max-w-5xl space-y-8 p-4 sm:p-8">
      {/* Stale data banner — shown when serving cached data due to API failure */}
      {stale && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-center text-sm text-amber-800">
          <p>
            Showing last saved data
            {staleMinutes != null && staleMinutes > 0 && (
              <span> ({staleMinutes} min ago)</span>
            )}
            .{" "}
            {retryCount >= 20
              ? "Server appears offline."
              : "Live data will load automatically once the server is back."}
          </p>
          <button
            onClick={() => {
              setRetryCount(0);
              load();
            }}
            className="mt-2 rounded bg-amber-600 px-3 py-1 text-xs font-medium text-white hover:bg-amber-700"
          >
            Retry Now
          </button>
        </div>
      )}

      {/* Refreshing indicator */}
      {refreshing && (
        <div className="fixed right-4 top-4 z-50 flex items-center gap-2 rounded-full bg-blue-600 px-3 py-1 text-xs text-white shadow">
          <div className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
          Updating...
        </div>
      )}

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

      {/* Top: Profile + Activity Rings */}
      <div className="grid gap-6 md:grid-cols-2">
        <PetProfileCard
          pet={data.pet}
          owner={data.owner}
          token={token}
          onUpdated={load}
        />
        <div className="flex flex-col items-center justify-center rounded-lg border bg-white p-6 shadow-sm">
          <h3 className="mb-4 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Activity Rings
          </h3>
          <ActivityRings records={data.preventive_records} />
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

      {/* Health Trends */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">Health Trends</h2>
        <HealthTrendsSection token={token} />
      </section>

      {/* Reminders */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">Upcoming Reminders</h2>
        <RemindersSection reminders={data.reminders} />
      </section>

      {/* Documents */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">Uploaded Documents</h2>
        <DocumentsSection documents={data.documents} token={token} onRefresh={load} />
      </section>

      {/* Footer */}
      <footer className="py-4 text-center text-xs text-gray-400">
        PetCircle — Preventive Pet Health System
      </footer>
    </div>
  );
}

export default function DashboardClient({ token }: { token: string }) {
  return (
    <ErrorBoundary>
      <DashboardInner token={token} />
    </ErrorBoundary>
  );
}
