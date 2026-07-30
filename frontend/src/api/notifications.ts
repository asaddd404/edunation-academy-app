import http from "@/api/http";
import type { Notification, Page, PageParams } from "@/types";

export function listNotifications(params?: PageParams) {
  return http.get<Page<Notification>>("/notifications", { params }).then((r) => r.data);
}

export function getUnreadCount() {
  return http.get<{ count: number }>("/notifications/unread-count").then((r) => r.data);
}

export function markNotificationRead(id: number) {
  return http.post<Notification>(`/notifications/${id}/read`).then((r) => r.data);
}

export function markAllNotificationsRead() {
  return http.post("/notifications/read-all");
}

export function deleteNotification(id: number) {
  return http.delete(`/notifications/${id}`);
}

export function clearAllNotifications() {
  return http.delete("/notifications");
}
