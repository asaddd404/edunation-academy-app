import http from "@/api/http";

export type TrashKind = "lesson" | "section";

export interface TrashEntry {
  id: number;
  kind: TrashKind;
  object_id: number;
  title: string;
  course_id: number;
  course: string;
  lesson_count: number;
  deleted_at: string;
  deleted_by: string | null;
  purge_at: string;
}

export function listTrash() {
  return http.get<TrashEntry[]>("/teacher/trash").then((r) => r.data);
}

export function restoreFromTrash(kind: TrashKind, objectId: number) {
  return http.post<{ message: string; course_id: number }>(`/teacher/trash/${kind}/${objectId}/restore`).then((r) => r.data);
}

export function deleteForever(kind: TrashKind, objectId: number) {
  return http.delete(`/teacher/trash/${kind}/${objectId}`);
}
