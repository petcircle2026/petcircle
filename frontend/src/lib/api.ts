/**
 * PetCircle — Backend API Client
 *
 * All backend API calls go through this module.
 * Base URL is set via NEXT_PUBLIC_API_URL environment variable.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface DashboardData {
  pet_name: string;
  species: string;
  breed: string;
  records: unknown[];
  reminders: unknown[];
  health_score: number | null;
}

/**
 * Fetch dashboard data for a given token.
 */
export async function fetchDashboard(token: string): Promise<DashboardData> {
  const res = await fetch(`${API_BASE}/dashboard/${token}`, {
    next: { revalidate: 60 },
  });

  if (!res.ok) {
    throw new Error(`Dashboard fetch failed: ${res.status}`);
  }

  return res.json();
}
