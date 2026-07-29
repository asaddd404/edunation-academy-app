import http from "@/api/http";
import type { AuthResponse, TokenPair, User } from "@/types";

export function register(payload: {
  phone: string;
  password: string;
  first_name: string;
  last_name: string;
}) {
  return http.post<AuthResponse>("/auth/register", payload).then((r) => r.data);
}

export function login(payload: { phone: string; password: string }) {
  return http.post<TokenPair>("/auth/login", payload).then((r) => r.data);
}

export function refreshTokens(refresh_token: string) {
  return http.post<TokenPair>("/auth/refresh", { refresh_token }).then((r) => r.data);
}

export function logout(refresh_token: string) {
  return http.post("/auth/logout", { refresh_token });
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
