import http from "@/api/http";
import type { CategoryAdmin, Page, PageParams, Role, User } from "@/types";

export function listUsers(params?: PageParams & { role?: Role }) {
  return http.get<Page<User>>("/admin/users", { params }).then((r) => r.data);
}

export function updateUser(id: number, payload: { role?: Role; is_active?: boolean }) {
  return http.patch<User>(`/admin/users/${id}`, payload).then((r) => r.data);
}

export function listCategoriesForAdmin(params?: PageParams) {
  return http.get<Page<CategoryAdmin>>("/admin/categories", { params }).then((r) => r.data);
}
