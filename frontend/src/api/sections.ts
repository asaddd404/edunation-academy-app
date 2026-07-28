import http from "@/api/http";
import type { Section, SectionTest, TestAttemptResult } from "@/types";

export function listSections(categoryId: number) {
  return http.get<Section[]>(`/categories/${categoryId}/sections`).then((r) => r.data);
}

export function listTeacherSections(categoryId: number) {
  return http.get<Section[]>(`/teacher/categories/${categoryId}/sections`).then((r) => r.data);
}

export function createSection(categoryId: number, payload: { title: string; description?: string }) {
  return http.post<Section>(`/teacher/categories/${categoryId}/sections`, payload).then((r) => r.data);
}

export function createSectionQuestion(
  sectionId: number,
  payload: { text: string; choices: { text: string; is_correct: boolean }[] },
) {
  return http.post(`/teacher/sections/${sectionId}/questions`, payload).then((r) => r.data);
}

export function getSectionTest(sectionId: number) {
  return http.get<SectionTest>(`/sections/${sectionId}/test`).then((r) => r.data);
}

export function submitSectionTestAttempt(
  sectionId: number,
  answers: { question_id: number; choice_id: number }[],
) {
  return http.post<TestAttemptResult>(`/sections/${sectionId}/test/attempts`, { answers }).then((r) => r.data);
}
