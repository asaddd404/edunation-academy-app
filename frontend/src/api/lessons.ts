import http from "@/api/http";
import type { LessonDetail, QuestionSavePayload, QuestionTeacher } from "@/types";

export function getLesson(lessonId: number) {
  return http.get<LessonDetail>(`/lessons/${lessonId}`).then((r) => r.data);
}

export function createLesson(
  sectionId: number,
  payload: { title: string; description?: string; homework_assignment?: string },
) {
  return http.post(`/teacher/sections/${sectionId}/lessons`, payload).then((r) => r.data);
}

export function updateLesson(
  lessonId: number,
  payload: { title?: string; description?: string; homework_assignment?: string; questions_per_attempt?: number },
) {
  return http.patch(`/teacher/lessons/${lessonId}`, payload).then((r) => r.data);
}

export function deleteLesson(lessonId: number) {
  return http.delete(`/teacher/lessons/${lessonId}`);
}

export function listLessonQuestions(lessonId: number) {
  return http.get<QuestionTeacher[]>(`/teacher/lessons/${lessonId}/questions`).then((r) => r.data);
}

export function createQuestion(lessonId: number, payload: QuestionSavePayload) {
  return http.post<QuestionTeacher>(`/teacher/lessons/${lessonId}/questions`, payload).then((r) => r.data);
}

/** Uploads an image to embed in a lesson's rich description/homework.
 * Returns the stored relative path, which goes into the document's image node. */
export function uploadLessonContentImage(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return http.post<{ path: string }>("/teacher/lesson-content/image", formData).then((r) => r.data.path);
}

/** Turns a stored `lesson-content/<uuid>.png` path into a fetchable URL.
 * Served by an unauthenticated route because <img src> can't send the bearer
 * token -- same arrangement as ЕНТ question images. */
export function getLessonContentImageUrl(path: string): string {
  const filename = path.startsWith("lesson-content/") ? path.slice("lesson-content/".length) : path;
  return `${import.meta.env.VITE_API_BASE_URL}/lesson-content/images/${filename}`;
}
