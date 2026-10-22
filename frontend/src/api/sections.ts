import http from "@/api/http";
import type { QuestionSavePayload, QuestionTeacher, Section, SectionTest, TestSession } from "@/types";

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

/** Opens an attempt at the section test, or resumes the open one. Submit
 * goes through `submitTestAttempt` in api/lessons, same as a lesson test. */
export function startSectionTest(sectionId: number) {
  return http.post<TestSession>(`/sections/${sectionId}/test/start`).then((r) => r.data);
}
