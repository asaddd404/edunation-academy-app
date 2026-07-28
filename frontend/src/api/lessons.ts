import http from "@/api/http";
import type { LessonDetail, TestAttemptResult } from "@/types";

export function getLesson(lessonId: number) {
  return http.get<LessonDetail>(`/lessons/${lessonId}`).then((r) => r.data);
}

export function createLesson(
  sectionId: number,
  payload: { title: string; description?: string; video_url?: string; homework_assignment?: string },
) {
  return http.post(`/teacher/sections/${sectionId}/lessons`, payload).then((r) => r.data);
}

export function createQuestion(
  lessonId: number,
  payload: { text: string; choices: { text: string; is_correct: boolean }[] },
) {
  return http.post(`/teacher/lessons/${lessonId}/questions`, payload).then((r) => r.data);
}

export function submitTestAttempt(lessonId: number, answers: { question_id: number; choice_id: number }[]) {
  return http.post<TestAttemptResult>(`/lessons/${lessonId}/test/attempts`, { answers }).then((r) => r.data);
}
