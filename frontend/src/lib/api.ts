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
  id: string;
  document_name: string | null;
  document_category: string | null;
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

export interface MonthlyCompletion {
  month: string;
  items_completed: number;
}

export interface ItemTimelineEntry {
  item_name: string;
  category: string;
  last_done_date: string;
  status: string;
}

export interface StatusSummary {
  total: number;
  up_to_date: number;
  upcoming: number;
  overdue: number;
  incomplete: number;
  cancelled: number;
}

export interface DiagnosticTrendEntry {
  month: string;
  count: number;
}

export interface HealthTrendsData {
  monthly_completions: MonthlyCompletion[];
  item_timeline: ItemTimelineEntry[];
  status_summary: StatusSummary;
  diagnostic_trends: DiagnosticTrendEntry[];
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
  document_name: string;
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

export interface AdminStats {
  users: { total: number; active: number; onboarding_complete: number; deleted: number };
  pets: { total: number; active: number; dogs: number; cats: number };
  documents: { total: number; success: number; pending: number; failed: number };
  preventive_records: { overdue: number; upcoming: number; up_to_date: number; cancelled: number };
  reminders: { total: number; pending: number; sent: number; completed: number; snoozed: number };
  conflicts: { pending: number };
  messages_24h: number;
}

// --- Dashboard Cache (localStorage) ---
// On success: cache the response so the dashboard can show last-known data
// if the backend is temporarily unavailable. Cache is per-token.

const CACHE_PREFIX = "petcircle_dash_";

function getCachedDashboard(token: string): { data: DashboardData; cachedAt: string } | null {
  try {
    const raw = localStorage.getItem(`${CACHE_PREFIX}${token}`);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function cacheDashboard(token: string, data: DashboardData): void {
  try {
    localStorage.setItem(
      `${CACHE_PREFIX}${token}`,
      JSON.stringify({ data, cachedAt: new Date().toISOString() })
    );
  } catch {
    // localStorage full or unavailable — ignore silently.
  }
}

// --- Dashboard API ---

/** Result from fetchDashboard — includes staleness info when serving cached data. */
export interface DashboardResult {
  data: DashboardData;
  /** True when data is served from cache because the API is unreachable. */
  stale: boolean;
  /** ISO timestamp of when the cached data was last fetched, if stale. */
  cachedAt?: string;
}

export async function fetchDashboard(token: string): Promise<DashboardResult> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30000);
  try {
    const res = await fetch(`${API_BASE}/dashboard/${token}`, {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!res.ok) {
      // 404 means token is invalid/expired — don't serve stale cache for this.
      // Parse the detail message from the backend for specific error context.
      if (res.status === 404) {
        const body = await res.json().catch(() => null);
        const detail = body?.detail || "Dashboard not found or link has expired.";
        throw new FetchError(detail, 404);
      }
      // 503 = backend temporarily unavailable — fall back to cache below.
      if (res.status === 503) {
        throw new FetchError("Server temporarily unavailable.", 503);
      }
      throw new FetchError(`Request failed: ${res.status}`, res.status);
    }
    const data: DashboardData = await res.json();
    // Cache the fresh response for offline/failure fallback.
    cacheDashboard(token, data);
    return { data, stale: false };
  } catch (e: any) {
    // For 404 (invalid token), never fall back to cache.
    if (e instanceof FetchError && e.status === 404) {
      throw e;
    }

    // For network errors, timeouts, 5xx — try serving cached data.
    const cached = getCachedDashboard(token);
    if (cached) {
      return { data: cached.data, stale: true, cachedAt: cached.cachedAt };
    }

    // No cache available — rethrow the original error.
    if (e.name === "AbortError") {
      throw new Error("Request timed out. Please try again.");
    }
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }
}

/** Error with HTTP status code so we can distinguish 404 from 5xx. */
class FetchError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "FetchError";
    this.status = status;
  }
}

export async function updateWeight(
  token: string,
  weight: number
): Promise<{ status: string; old_weight: number | null; new_weight: number }> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(`${API_BASE}/dashboard/${token}/weight`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ weight }),
      signal: controller.signal,
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail || `Request failed: ${res.status}`);
    }
    return res.json();
  } catch (e: any) {
    if (e.name === "AbortError") {
      throw new Error("Request timed out. Please try again.");
    }
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }
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
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(`${API_BASE}/dashboard/${token}/preventive`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item_name, last_done_date }),
      signal: controller.signal,
    });
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail || `Request failed: ${res.status}`);
    }
    return res.json();
  } catch (e: any) {
    if (e.name === "AbortError") {
      throw new Error("Request timed out. Please try again.");
    }
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function retryExtraction(
  token: string,
  documentId: string
): Promise<{ status: string; document_id: string }> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 120000);
  try {
    const res = await fetch(
      `${API_BASE}/dashboard/${token}/retry-extraction/${documentId}`,
      {
        method: "POST",
        signal: controller.signal,
      }
    );
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail || `Request failed: ${res.status}`);
    }
    return res.json();
  } catch (e: any) {
    if (e.name === "AbortError") {
      throw new Error("Extraction timed out. Please try again.");
    }
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchHealthTrends(token: string): Promise<HealthTrendsData> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(`${API_BASE}/dashboard/${token}/trends`, {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!res.ok) {
      throw new Error(`Request failed: ${res.status}`);
    }
    return res.json();
  } catch (e: any) {
    if (e.name === "AbortError") {
      throw new Error("Request timed out. Please try again.");
    }
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Authenticate to the admin dashboard with a password.
 * On success, returns the admin API key for subsequent requests.
 * Throws on invalid password or network error.
 */
export async function adminLogin(password: string): Promise<string> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10000);
  try {
    const res = await fetch(`${API_BASE}/admin/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
      signal: controller.signal,
    });
    if (res.status === 403) {
      throw new Error("Invalid password.");
    }
    if (!res.ok) {
      throw new Error(`Request failed: ${res.status}`);
    }
    const data = await res.json();
    return data.admin_key;
  } catch (e: any) {
    if (e.name === "AbortError") {
      throw new Error("Request timed out. Please try again.");
    }
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }
}

// --- Admin API ---

async function adminFetch<T>(path: string, adminKey: string): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 30000);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { "X-ADMIN-KEY": adminKey },
      cache: "no-store",
      signal: controller.signal,
    });
    if (res.status === 403) throw new Error("Invalid admin key.");
    if (!res.ok) throw new Error(`Request failed: ${res.status}`);
    return res.json();
  } catch (e: any) {
    if (e.name === "AbortError") {
      throw new Error("Request timed out. Please try again.");
    }
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function adminMutate<T>(
  path: string,
  adminKey: string,
  method: "PATCH" | "POST",
  body?: unknown
): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: {
        "X-ADMIN-KEY": adminKey,
        "Content-Type": "application/json",
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    if (res.status === 403) throw new Error("Invalid admin key.");
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new Error(data?.detail || `Request failed: ${res.status}`);
    }
    return res.json();
  } catch (e: any) {
    if (e.name === "AbortError") {
      throw new Error("Request timed out. Please try again.");
    }
    throw e;
  } finally {
    clearTimeout(timeoutId);
  }
}

export const adminApi = {
  getStats: (key: string) => adminFetch<AdminStats>("/admin/stats", key),
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
