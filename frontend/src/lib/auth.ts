const TOKEN_KEY = "mh_auth_token";
const ROLE_KEY = "mh_user_role";
const USERNAME_KEY = "mh_username";

export interface AuthToken {
  access_token: string;
  token_type: string;
  expires_in: number;
  role?: string;
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function setUserInfo(username: string, role: string): void {
  localStorage.setItem(USERNAME_KEY, username);
  localStorage.setItem(ROLE_KEY, role);
}

export function getUserRole(): string {
  if (typeof window === "undefined") return "admin";
  return localStorage.getItem(ROLE_KEY) || "admin";
}

export function getUsername(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(USERNAME_KEY) || "";
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(ROLE_KEY);
  localStorage.removeItem(USERNAME_KEY);
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

export function getAuthHeaders(): HeadersInit {
  const token = getToken();
  if (!token) return {};
  return {
    Authorization: `Bearer ${token}`,
  };
}
