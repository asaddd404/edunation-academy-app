import http from "@/api/http";
import type { QuestionSavePayload, QuestionTeacher } from "@/types";

// Shared by lesson mini-test and section-test questions -- both live under
// the same /teacher/questions/{id} endpoint regardless of which owns them.
// PUT: the server replaces the whole question (options included) each save.
export function updateQuestion(questionId: number, payload: QuestionSavePayload) {
  return http.put<QuestionTeacher>(`/teacher/questions/${questionId}`, payload).then((r) => r.data);
}

export function deleteQuestion(questionId: number) {
  return http.delete(`/teacher/questions/${questionId}`);
}
