"use client";

import { useEffect, useState } from "react";
import type { AdminStats } from "@/lib/api";
import { adminApi } from "@/lib/api";

interface StatCardProps {
  label: string;
  value: number;
  color?: "green" | "red" | "amber" | "blue" | "purple" | "gray";
  /** When true, only apply the color when value > 0 (for problem indicators). */
  alertOnly?: boolean;
}

function StatCard({ label, value, color = "gray", alertOnly = false }: StatCardProps) {
  const active = !alertOnly || value > 0;
  const colorMap = {
    green: active ? "border-green-400 bg-green-50 text-green-700" : "border-gray-200 bg-white text-gray-600",
    red: active ? "border-red-400 bg-red-50 text-red-700" : "border-gray-200 bg-white text-gray-600",
    amber: active ? "border-amber-400 bg-amber-50 text-amber-700" : "border-gray-200 bg-white text-gray-600",
    blue: active ? "border-blue-400 bg-blue-50 text-blue-700" : "border-gray-200 bg-white text-gray-600",
    purple: active ? "border-purple-400 bg-purple-50 text-purple-700" : "border-gray-200 bg-white text-gray-600",
    gray: "border-gray-200 bg-white text-gray-600",
  };

  return (
    <div className={`rounded-lg border-2 p-4 ${colorMap[color]}`}>
      <p className="text-sm font-medium opacity-75">{label}</p>
      <p className="mt-1 text-2xl font-bold">{value}</p>
    </div>
  );
}

export default function OverviewPanel({ adminKey }: { adminKey: string }) {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    setError("");
    adminApi
      .getStats(adminKey)
      .then(setStats)
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false));
  }, [adminKey]);

  if (loading)
    return <p className="py-8 text-center text-gray-500">Loading stats...</p>;
  if (error)
    return <p className="py-8 text-center text-red-600">{error}</p>;
  if (!stats) return null;

  return (
    <div className="space-y-8">
      {/* Users & Pets */}
      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
          Users &amp; Pets
        </h2>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Active Users" value={stats.users.active} color="blue" />
          <StatCard label="Onboarding Complete" value={stats.users.onboarding_complete} color="green" />
          <StatCard label="Active Pets" value={stats.pets.active} color="blue" />
          <StatCard label="Dogs" value={stats.pets.dogs} color="gray" />
          <StatCard label="Cats" value={stats.pets.cats} color="gray" />
          <StatCard label="Deleted Users" value={stats.users.deleted} color="red" alertOnly />
        </div>
      </section>

      {/* Document Extraction */}
      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
          Document Extraction
        </h2>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Total Documents" value={stats.documents.total} color="gray" />
          <StatCard label="Success" value={stats.documents.success} color="green" />
          <StatCard label="Pending" value={stats.documents.pending} color="amber" alertOnly />
          <StatCard label="Failed" value={stats.documents.failed} color="red" alertOnly />
        </div>
      </section>

      {/* Preventive Health */}
      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
          Preventive Health
        </h2>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Overdue" value={stats.preventive_records.overdue} color="red" alertOnly />
          <StatCard label="Upcoming" value={stats.preventive_records.upcoming} color="amber" alertOnly />
          <StatCard label="Up to Date" value={stats.preventive_records.up_to_date} color="green" />
          <StatCard label="Pending Conflicts" value={stats.conflicts.pending} color="red" alertOnly />
        </div>
      </section>

      {/* Orders */}
      {stats.orders && (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
            Orders
          </h2>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="Total Orders" value={stats.orders.total} color="gray" />
            <StatCard label="Pending" value={stats.orders.pending} color="amber" alertOnly />
            <StatCard label="Fulfilled" value={stats.orders.completed} color="green" />
            <StatCard label="Cancelled" value={stats.orders.cancelled} color="red" alertOnly />
          </div>
        </section>
      )}

      {/* Reminders & Activity */}
      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
          Reminders &amp; Activity
        </h2>
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Sent" value={stats.reminders.sent} color="blue" />
          <StatCard label="Completed" value={stats.reminders.completed} color="green" />
          <StatCard label="Snoozed" value={stats.reminders.snoozed} color="purple" />
          <StatCard label="Messages (24h)" value={stats.messages_24h} color="blue" />
        </div>
      </section>
    </div>
  );
}
