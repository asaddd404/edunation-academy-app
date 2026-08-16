import http from "@/api/http";

export interface TodayActivity {
  total_seconds: number;
}

export function pingActivity() {
  return http.post<TodayActivity>("/activity/ping").then((r) => r.data);
}

export function getMyTodayActivity() {
  return http.get<TodayActivity>("/activity/me/today").then((r) => r.data);
}
