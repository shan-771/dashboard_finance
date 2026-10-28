export type ApiRole = "manager" | "staff";

export type ApiUser = {
  id: string;
  user_id: string;
  email: string;
  display_name: string;
  role: ApiRole;
  is_active: boolean;
};

export type AuthResponse = {
  user: ApiUser;
  csrf_token: string;
};

export type CreateStaffPayload = {
  user_id: string;
  email: string;
  password: string;
};

export type ApiEnquiry = {
  id: string;
  customer: ApiCustomer;
  service_type: string;
  source: string;
  status: "New" | "Assigned" | "Attended" | "Follow-ups" | "Closed" | "Open" | "Lost";
  handled_by_id: string | null;
  handled_by_name: string | null;
  notes: string | null;
  outcome_reason: string | null;
  do_not_contact: boolean;
  next_follow_up_at: string | null;
  completed_follow_up_count: number;
  created_at: string;
  updated_at: string;
};
export type ApiDeletedEnquiry = ApiEnquiry & { deleted_at: string; purge_at: string };

export type ApiCustomer = { id: string; name: string; phone: string; email: string | null; created_at: string };
export type ApiChangeRequest = {
  id: string;
  enquiry_id: string;
  request_type: "edit" | "delete";
  status: "pending" | "approved" | "rejected" | "stale" | "completed";
  original_snapshot: Record<string, unknown>;
  reason: string | null;
  decision_note: string | null;
  submitted_by_name: string | null;
  decided_by_name: string | null;
  created_at: string;
};

export type ApiPage<T> = { items: T[]; total: number; limit: number; offset: number };
export type FollowUpBucket = "due-today" | "upcoming" | "overdue";
export type DatabaseHealth = { status: string; database: string; business_timezone: string };

export type CreateEnquiryPayload = {
  customer: { name: string; phone: string; email?: string };
  service_type: string;
  source: string;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}, csrfToken?: string): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (csrfToken) headers.set("X-CSRF-Token", csrfToken);

  const response = await fetch(path, { ...init, headers, credentials: "include" });
  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body?.detail;
    const message = typeof detail === "string" ? detail : `Request failed (${response.status})`;
    throw new ApiError(response.status, message);
  }
  return body as T;
}

export const api = {
  login: (user_id: string, password: string) =>
    request<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ user_id, password }),
    }),
  me: () => request<AuthResponse>("/auth/me"),
  logout: (csrfToken: string) =>
    request<void>("/auth/logout", { method: "POST" }, csrfToken),
  listUsers: () => request<ApiUser[]>("/users"),
  createStaff: (payload: CreateStaffPayload, csrfToken: string) =>
    request<ApiUser>("/users", { method: "POST", body: JSON.stringify(payload) }, csrfToken),
  setStaffActive: (id: string, is_active: boolean, csrfToken: string) =>
    request<ApiUser>(
      `/users/${encodeURIComponent(id)}/status`,
      { method: "PATCH", body: JSON.stringify({ is_active }) },
      csrfToken,
    ),
  listEnquiries: () => request<ApiPage<ApiEnquiry>>("/enquiries?limit=100&offset=0"),
  claimEnquiry: (enquiryId: string, csrfToken: string) =>
    request<ApiEnquiry>(`/enquiries/${encodeURIComponent(enquiryId)}/claim`, { method: "POST", body: JSON.stringify({}) }, csrfToken),
  updateEnquiryStatus: (enquiryId: string, payload: { status: "Closed" | "Open" | "Lost"; outcome_reason?: string; do_not_contact?: boolean }, csrfToken: string) =>
    request<ApiEnquiry>(`/enquiries/${encodeURIComponent(enquiryId)}/status`, { method: "PATCH", body: JSON.stringify(payload) }, csrfToken),
  saveEnquiryContact: (enquiryId: string, payload: { notes: string; next_follow_up_at: string }, csrfToken: string) =>
    request<ApiEnquiry>(`/enquiries/${encodeURIComponent(enquiryId)}/contact`, { method: "PUT", body: JSON.stringify(payload) }, csrfToken),
  listCustomers: () => request<ApiCustomer[]>("/customers?limit=100&offset=0"),
  requestEnquiryDeletion: (enquiryId: string, csrfToken: string) =>
    request<ApiChangeRequest>(`/enquiries/${encodeURIComponent(enquiryId)}/change-requests`, { method: "POST", body: JSON.stringify({ request_type: "delete" }) }, csrfToken),
  getEnquiryDeletionRequest: (enquiryId: string) =>
    request<ApiChangeRequest | null>(`/enquiries/${encodeURIComponent(enquiryId)}/change-requests`),
  listChangeRequests: (status: "pending" | "approved") =>
    request<{ items: ApiChangeRequest[]; total: number; limit: number; offset: number }>(`/change-requests?status=${status}&limit=100&offset=0`),
  listDeletedEnquiries: () =>
    request<{ items: ApiDeletedEnquiry[]; total: number; limit: number; offset: number }>("/enquiries/deleted?limit=100&offset=0"),
  restoreDeletedEnquiry: (enquiryId: string, csrfToken: string) =>
    request<ApiEnquiry>(`/enquiries/${encodeURIComponent(enquiryId)}/restore`, { method: "POST", body: JSON.stringify({}) }, csrfToken),
  permanentlyDeleteEnquiry: (enquiryId: string, csrfToken: string) =>
    request<{ enquiry_id: string; customer_deleted: boolean; permanently_deleted: boolean }>(`/enquiries/${encodeURIComponent(enquiryId)}/permanent`, { method: "DELETE" }, csrfToken),
  decideChangeRequest: (requestId: string, decision: "approve" | "reject", csrfToken: string) =>
    request<ApiChangeRequest>(`/change-requests/${encodeURIComponent(requestId)}`, { method: "PATCH", body: JSON.stringify({ decision }) }, csrfToken),
  confirmEnquiryDeletion: (requestId: string, csrfToken: string) =>
    request<ApiChangeRequest>(`/change-requests/${encodeURIComponent(requestId)}/confirm-deletion`, { method: "POST", body: JSON.stringify({}) }, csrfToken),
  createEnquiry: (payload: CreateEnquiryPayload, csrfToken: string) =>
    request<ApiEnquiry>("/enquiries", { method: "POST", body: JSON.stringify(payload) }, csrfToken),
  databaseHealth: () => request<DatabaseHealth>("/health/database"),
  listFollowUps: (bucket: FollowUpBucket) =>
    request<ApiPage<ApiEnquiry> & { bucket: FollowUpBucket }>(`/follow-ups?bucket=${bucket}&limit=100&offset=0`),
  completeFollowUp: (enquiryId: string, csrfToken: string) =>
    request<{ id: string }>(`/enquiries/${encodeURIComponent(enquiryId)}/follow-ups`, { method: "POST", body: JSON.stringify({}) }, csrfToken),
  scheduleFollowUp: (enquiryId: string, nextFollowUpAt: string | null, csrfToken: string) =>
    request<ApiEnquiry>(
      `/enquiries/${encodeURIComponent(enquiryId)}/follow-up`,
      { method: "PUT", body: JSON.stringify({ next_follow_up_at: nextFollowUpAt }) },
      csrfToken,
    ),
};
