import http from "@/api/http";
import type { QuestionSavePayload, QuestionTeacher, Section } from "@/types";

export function listSections(categoryId: number) {
  return http.get<Section[]>(`/categories/${categoryId}/sections`).then((r) => r.data);
}

export function listTeacherSections(categoryId: number) {
  return http.get<Section[]>(`/teacher/categories/${categoryId}/sections`).then((r) => r.data);
}

export function createSection(categoryId: number, payload: { title: string; description?: string }) {
  return http.post<Section>(`/teacher/categories/${categoryId}/sections`, payload).then((r) => r.data);
}

export function updateSection(
  sectionId: number,
  payload: { title?: string; description?: string; questions_per_attempt?: number },
) {
  return http.patch<Section>(`/teacher/sections/${sectionId}`, payload).then((r) => r.data);
}

export function deleteSection(sectionId: number) {
  return http.delete(`/teacher/sections/${sectionId}`);
}

export function listSectionQuestions(sectionId: number) {
  return http.get<QuestionTeacher[]>(`/teacher/sections/${sectionId}/questions`).then((r) => r.data);
}

export function createSectionQuestion(sectionId: number, payload: QuestionSavePayload) {
  return http.post<QuestionTeacher>(`/teacher/sections/${sectionId}/questions`, payload).then((r) => r.data);
}
