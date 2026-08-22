import http from "@/api/http";
import type { AccessToken, AuthResponse, User } from "@/types";

export function register(payload: {
  phone: string;
  password: string;
  first_name: string;
  last_name: string;
}) {
  return http.post<AuthResponse>("/auth/register", payload).then((r) => r.data);
}

export function login(payload: { phone: string; password: string }) {
  return http.post<AccessToken>("/auth/login", payload).then((r) => r.data);
}

/**
 * Normally sends nothing: the refresh token rides along as an httpOnly
 * cookie, which is the whole point -- this code cannot read it, and neither
 * can anything injected into the page.
 *
 * `legacyToken` is the one exception, and it is temporary. Sessions created
 * before the cookie switch live in localStorage, and handing one back on the
 * first load is what converts it into a cookie instead of signing the user
 * out. Remove the parameter once the backend stops accepting a body.
 */
export function refreshTokens(legacyToken?: string) {
  const body = legacyToken ? { refresh_token: legacyToken } : undefined;
  return http.post<AccessToken>("/auth/refresh", body).then((r) => r.data);
}

export function logout() {
  return http.post("/auth/logout");
}

export function changePassword(payload: { old_password: string; new_password: string }) {
  // The server ends every session on a password change and immediately issues
  // a replacement, so the response carries a fresh access token and a
  // Set-Cookie for the new refresh token. Adopt the access token or the next
  // request signs this tab out.
  return http.post<AccessToken>("/auth/change-password", payload).then((r) => r.data);
}

export function fetchMe() {
  return http.get<User>("/auth/me").then((r) => r.data);
}

export function updateProfile(payload: { first_name?: string; last_name?: string; phone?: string }) {
  return http.patch<User>("/me", payload).then((r) => r.data);
}

export function uploadAvatar(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return http.post<User>("/me/avatar", formData).then((r) => r.data);
}

export function deleteAvatar() {
  return http.delete<User>("/me/avatar").then((r) => r.data);
}

export function getAvatarUrl(userId: number) {
  return `${import.meta.env.VITE_API_BASE_URL}/users/${userId}/avatar`;
}
