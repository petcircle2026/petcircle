import { fetchDashboard } from "@/lib/api";

interface DashboardPageProps {
  params: { token: string };
}

export default async function DashboardPage({ params }: DashboardPageProps) {
  // TODO: Fetch dashboard data from backend API
  const { token } = params;

  return (
    <main className="min-h-screen p-8">
      <h1 className="text-2xl font-bold">Pet Health Dashboard</h1>
      <p className="mt-2 text-gray-500">Token: {token}</p>
      <p className="mt-4 text-gray-400">
        Dashboard content will be implemented in Phase 5B.
      </p>
    </main>
  );
}
