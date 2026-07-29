import http from "@/api/http";
import type { CategoryAdmin, Role, User } from "@/types";

export function listUsers(role?: Role) {
  return http.get<User[]>("/admin/users", { params: role ? { role } : undefined }).then((r) => r.data);
}

export function updateUser(id: number, payload: { role?: Role; is_active?: boolean }) {
  return http.patch<User>(`/admin/users/${id}`, payload).then((r) => r.data);
}

export function listCategoriesForAdmin() {
  return http.get<CategoryAdmin[]>("/admin/categories").then((r) => r.data);
}
