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
