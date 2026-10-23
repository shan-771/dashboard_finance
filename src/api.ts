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
};
