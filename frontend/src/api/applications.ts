import http from "@/api/http";
import type { Application } from "@/types";

export function applyToCategory(categoryId: number) {
  return http.post<Application>("/applications", { category_id: categoryId }).then((r) => r.data);
}

export function listMyApplications() {
  return http.get<Application[]>("/applications/me").then((r) => r.data);
}

export function listPendingApplications() {
  return http.get<Application[]>("/applications/pending").then((r) => r.data);
}

export function approveApplication(id: number) {
  return http.post<Application>(`/applications/${id}/approve`).then((r) => r.data);
}

export function rejectApplication(id: number) {
  return http.post<Application>(`/applications/${id}/reject`).then((r) => r.data);
}

export function listAllApplications(params?: { status?: string; category_id?: number }) {
  return http.get<Application[]>("/applications", { params }).then((r) => r.data);
}
