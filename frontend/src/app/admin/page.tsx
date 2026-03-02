"use client";

import { useState } from "react";
import AdminDashboard from "@/components/admin/AdminDashboard";
import { verifyAdminKey } from "@/lib/api";

export default function AdminPage() {
  const [adminKey, setAdminKey] = useState("");
  const [authenticated, setAuthenticated] = useState(false);
  const [input, setInput] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    const key = input.trim();
    if (!key) return;

    setError("");
    setLoading(true);

    try {
      const valid = await verifyAdminKey(key);
      if (valid) {
        setAdminKey(key);
        setAuthenticated(true);
      } else {
        setError("Invalid admin key. Please try again.");
      }
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (authenticated) {
    return (
      <AdminDashboard
        adminKey={adminKey}
        onLogout={() => {
          setAdminKey("");
          setAuthenticated(false);
          setInput("");
          setError("");
        }}
      />
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 p-4">
      <form
        onSubmit={handleLogin}
        className="w-full max-w-sm rounded-lg border bg-white p-8 shadow-sm"
      >
        <h1 className="mb-6 text-center text-xl font-bold">
          PetCircle Admin
        </h1>
        <label className="mb-2 block text-sm font-medium text-gray-700">
          Admin Key
        </label>
        <input
          type="password"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Enter admin secret key"
          className="mb-4 w-full rounded border px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          autoFocus
          disabled={loading}
        />
        {error && (
          <p className="mb-4 text-sm text-red-600">{error}</p>
        )}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded bg-blue-600 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Verifying..." : "Sign In"}
        </button>
      </form>
    </div>
  );
}
