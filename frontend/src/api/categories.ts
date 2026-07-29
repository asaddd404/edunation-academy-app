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

export function uploadCategoryImage(id: number, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return http.post<Category>(`/teacher/categories/${id}/image`, formData).then((r) => r.data);
}

export function deleteCategoryImage(id: number) {
  return http.delete<Category>(`/teacher/categories/${id}/image`).then((r) => r.data);
}

export function getCategoryImageUrl(id: number) {
  return `${import.meta.env.VITE_API_BASE_URL}/categories/${id}/image`;
}
