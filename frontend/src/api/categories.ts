import http from "@/api/http";
import type { Category } from "@/types";

export function listCategories() {
  return http.get<Category[]>("/categories").then((r) => r.data);
}

export function getCategory(id: number) {
  return http.get<Category>(`/categories/${id}`).then((r) => r.data);
}

export function createCategory(payload: { name: string; slug?: string; description?: string }) {
  return http.post<Category>("/admin/categories", payload).then((r) => r.data);
}

export function assignTeacher(categoryId: number, teacherId: number) {
  return http.post(`/admin/categories/${categoryId}/assign-teacher`, { teacher_id: teacherId });
}

export function unassignTeacher(categoryId: number, teacherId: number) {
  return http.delete(`/admin/categories/${categoryId}/teachers/${teacherId}`);
}

export function listMyTeachingCategories() {
  return http.get<Category[]>("/teacher/categories").then((r) => r.data);
}

export function getTeacherCategory(id: number) {
  return http.get<Category>(`/teacher/categories/${id}`).then((r) => r.data);
}

export function updateTeacherCategory(id: number, payload: { description?: string }) {
  return http.patch<Category>(`/teacher/categories/${id}`, payload).then((r) => r.data);
}
