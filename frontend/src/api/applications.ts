import http from "@/api/http";
import type { Application, Page, PageParams } from "@/types";

export function applyToCategory(categoryId: number) {
  return http.post<Application>("/applications", { category_id: categoryId }).then((r) => r.data);
}

export function listMyApplications(params?: PageParams) {
  return http.get<Page<Application>>("/applications/me", { params }).then((r) => r.data);
}

export function listPendingApplications(params?: PageParams) {
  return http.get<Page<Application>>("/applications/pending", { params }).then((r) => r.data);
}

export function approveApplication(id: number) {
  return http.post<Application>(`/applications/${id}/approve`).then((r) => r.data);
}

export function rejectApplication(id: number) {
  return http.post<Application>(`/applications/${id}/reject`).then((r) => r.data);
}

export function listAllApplications(params?: PageParams & { status?: string; category_id?: number }) {
  return http.get<Page<Application>>("/applications", { params }).then((r) => r.data);
}
