"use client";

import { useState } from "react";
import AdminDashboard from "@/components/admin/AdminDashboard";

export default function AdminPage() {
  const [adminKey, setAdminKey] = useState("");
  const [authenticated, setAuthenticated] = useState(false);
  const [input, setInput] = useState("");

  function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    if (input.trim()) {
      setAdminKey(input.trim());
      setAuthenticated(true);
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
        />
        <button
          type="submit"
          className="w-full rounded bg-blue-600 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Sign In
        </button>
      </form>
    </div>
  );
}
