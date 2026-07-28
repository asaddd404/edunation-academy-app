import http from "@/api/http";
import type { Section } from "@/types";

export function listSections(categoryId: number) {
  return http.get<Section[]>(`/categories/${categoryId}/sections`).then((r) => r.data);
}

export function listTeacherSections(categoryId: number) {
  return http.get<Section[]>(`/teacher/categories/${categoryId}/sections`).then((r) => r.data);
}

export function createSection(categoryId: number, payload: { title: string; description?: string }) {
  return http.post<Section>(`/teacher/categories/${categoryId}/sections`, payload).then((r) => r.data);
}
