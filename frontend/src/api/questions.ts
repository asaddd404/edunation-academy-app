import http from "@/api/http";
import type { QuestionSavePayload, QuestionTeacher } from "@/types";

// Shared by lesson mini-test and section-test questions -- both live under
// the same /teacher/questions/{id} endpoint regardless of which owns them.
export function updateQuestion(questionId: number, payload: QuestionSavePayload) {
  return http.patch<QuestionTeacher>(`/teacher/questions/${questionId}`, payload).then((r) => r.data);
}

export function deleteQuestion(questionId: number) {
  return http.delete(`/teacher/questions/${questionId}`);
}
