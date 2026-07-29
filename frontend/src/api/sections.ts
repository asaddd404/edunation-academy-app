import http from "@/api/http";
import type { AnswerPayload, QuestionSavePayload, QuestionTeacher, Section, SectionTest, TestAttemptResult } from "@/types";

export function listSections(categoryId: number) {
  return http.get<Section[]>(`/categories/${categoryId}/sections`).then((r) => r.data);
}

export function listTeacherSections(categoryId: number) {
  return http.get<Section[]>(`/teacher/categories/${categoryId}/sections`).then((r) => r.data);
}

export function createSection(categoryId: number, payload: { title: string; description?: string }) {
  return http.post<Section>(`/teacher/categories/${categoryId}/sections`, payload).then((r) => r.data);
}

export function updateSection(sectionId: number, payload: { title?: string; description?: string }) {
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

export function getSectionTest(sectionId: number) {
  return http.get<SectionTest>(`/sections/${sectionId}/test`).then((r) => r.data);
}

export function submitSectionTestAttempt(sectionId: number, answers: AnswerPayload[]) {
  return http.post<TestAttemptResult>(`/sections/${sectionId}/test/attempts`, { answers }).then((r) => r.data);
}
