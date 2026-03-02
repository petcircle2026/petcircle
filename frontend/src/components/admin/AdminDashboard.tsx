"use client";

import { useState } from "react";
import UsersPanel from "./UsersPanel";
import PetsPanel from "./PetsPanel";
import RemindersPanel from "./RemindersPanel";
import DocumentsPanel from "./DocumentsPanel";
import MessagesPanel from "./MessagesPanel";

const TABS = ["Users", "Pets", "Reminders", "Documents", "Messages"] as const;
type Tab = (typeof TABS)[number];

interface Props {
  adminKey: string;
  onLogout: () => void;
}

export default function AdminDashboard({ adminKey, onLogout }: Props) {
  const [tab, setTab] = useState<Tab>("Users");

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b bg-white px-6 py-4 shadow-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <h1 className="text-lg font-bold">PetCircle Admin</h1>
          <button
            onClick={onLogout}
            className="rounded border px-3 py-1 text-sm text-gray-600 hover:bg-gray-100"
          >
            Logout
          </button>
        </div>
      </header>

      {/* Tabs */}
      <div className="border-b bg-white">
        <nav className="mx-auto flex max-w-7xl gap-1 px-6">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
                tab === t
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {t}
            </button>
          ))}
        </nav>
      </div>

      {/* Content */}
      <main className="mx-auto max-w-7xl p-6">
        {tab === "Users" && <UsersPanel adminKey={adminKey} />}
        {tab === "Pets" && <PetsPanel adminKey={adminKey} />}
        {tab === "Reminders" && <RemindersPanel adminKey={adminKey} />}
        {tab === "Documents" && <DocumentsPanel adminKey={adminKey} />}
        {tab === "Messages" && <MessagesPanel adminKey={adminKey} />}
      </main>
    </div>
  );
}
