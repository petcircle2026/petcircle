/**
 * PetCircle — Backend API Client
 *
 * All backend API calls go through this module.
 * Base URL is set via NEXT_PUBLIC_API_URL environment variable.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// --- Dashboard Types (match backend response shapes) ---

export interface PetProfile {
  name: string;
  species: string;
  breed: string;
  gender: string;
  dob: string | null;
  weight: number | null;
  neutered: boolean;
}

export interface OwnerInfo {
  full_name: string | null;
}

export interface PreventiveRecord {
  item_name: string;
  category: string;
  last_done_date: string | null;
  next_due_date: string | null;
  status: string;
  recurrence_days: number;
}

export interface ReminderItem {
  item_name: string;
  next_due_date: string;
  status: string;
  sent_at: string | null;
}

export interface DocumentItem {
  mime_type: string;
  extraction_status: string;
  uploaded_at: string | null;
}

export interface HealthScore {
  score: number;
  essential_done: number;
  essential_total: number;
  complementary_done: number;
  complementary_total: number;
}

export interface DashboardData {
  pet: PetProfile;
  owner: OwnerInfo;
  preventive_records: PreventiveRecord[];
  reminders: ReminderItem[];
  documents: DocumentItem[];
  health_score: HealthScore;
}

// --- Admin Types ---

export interface AdminUser {
  id: string;
  mobile_number: string;
  full_name: string | null;
  pincode: string | null;
  email: string | null;
  consent_given: boolean;
  onboarding_state: string;
  is_deleted: boolean;
  created_at: string;
}

export interface AdminPet {
  id: string;
  user_id: string;
  name: string;
  species: string;
  breed: string;
  gender: string;
  dob: string | null;
  weight: number | null;
  neutered: boolean;
  is_deleted: boolean;
  created_at: string;
}

export interface AdminReminder {
  id: string;
  pet_name: string;
  item_name: string;
  next_due_date: string;
  record_status: string;
  reminder_status: string;
  sent_at: string | null;
  created_at: string;
}

export interface AdminDocument {
  id: string;
  pet_id: string;
  pet_name: string;
  file_path: string;
  mime_type: string;
  extraction_status: string;
  created_at: string;
}

export interface AdminMessage {
  id: string;
  mobile_number: string;
  direction: string;
  message_type: string;
  payload: string;
  created_at: string;
}

// --- Dashboard API ---

export async function fetchDashboard(token: string): Promise<DashboardData> {
  const res = await fetch(`${API_BASE}/dashboard/${token}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(
      res.status === 404
        ? "Dashboard not found or link has expired."
        : `Request failed: ${res.status}`
    );
  }
  return res.json();
}

export async function updateWeight(
  token: string,
  weight: number
): Promise<{ status: string; old_weight: number | null; new_weight: number }> {
  const res = await fetch(`${API_BASE}/dashboard/${token}/weight`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ weight }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export async function updatePreventiveDate(
  token: string,
  item_name: string,
  last_done_date: string
): Promise<{
  status: string;
  item_name: string;
  new_last_done_date: string;
  new_next_due_date: string;
  record_status: string;
}> {
  const res = await fetch(`${API_BASE}/dashboard/${token}/preventive`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ item_name, last_done_date }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

// --- Admin API ---

async function adminFetch<T>(path: string, adminKey: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "X-ADMIN-KEY": adminKey },
    cache: "no-store",
  });
  if (res.status === 403) throw new Error("Invalid admin key.");
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

async function adminMutate<T>(
  path: string,
  adminKey: string,
  method: "PATCH" | "POST",
  body?: unknown
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      "X-ADMIN-KEY": adminKey,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 403) throw new Error("Invalid admin key.");
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export const adminApi = {
  getUsers: (key: string) => adminFetch<AdminUser[]>("/admin/users", key),
  getPets: (key: string) => adminFetch<AdminPet[]>("/admin/pets", key),
  getReminders: (key: string) =>
    adminFetch<AdminReminder[]>("/admin/reminders", key),
  getDocuments: (key: string) =>
    adminFetch<AdminDocument[]>("/admin/documents", key),
  getMessages: (key: string, direction?: string, limit?: number) => {
    const params = new URLSearchParams();
    if (direction) params.set("direction", direction);
    if (limit) params.set("limit", String(limit));
    const qs = params.toString();
    return adminFetch<AdminMessage[]>(
      `/admin/messages${qs ? `?${qs}` : ""}`,
      key
    );
  },
  softDeleteUser: (key: string, userId: string) =>
    adminMutate(`/admin/soft-delete-user/${userId}`, key, "PATCH"),
  revokeToken: (key: string, petId: string) =>
    adminMutate(`/admin/revoke-token/${petId}`, key, "PATCH"),
  triggerReminder: (key: string, petId: string) =>
    adminMutate(`/admin/trigger-reminder/${petId}`, key, "POST"),
};
