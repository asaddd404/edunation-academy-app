import http from "@/api/http";
import type { TeacherToday } from "@/types/teacherToday";

export function getTeacherToday() {
  return http.get<TeacherToday>("/teacher/today").then((r) => r.data);
}
