import http from "@/api/http";
import type {
  HwAnswers,
  HwAttempt,
  HwProblem,
  HwResults,
  HwSettings,
  HwState,
  HwStudentDetail,
  HwTask,
  HwTaskData,
  HwTaskType,
  HwTeacherHomework,
} from "@/types/autoHomework";

// ── Teacher: constructor ──

export function getTeacherHomework(lessonId: number) {
  return http.get<HwTeacherHomework>(`/teacher/lessons/${lessonId}/auto-homework`).then((r) => r.data);
}

export function saveHomeworkSettings(lessonId: number, settings: HwSettings) {
  return http.patch<HwSettings>(`/teacher/lessons/${lessonId}/auto-homework/settings`, settings).then((r) => r.data);
}

export function addTimeToOpenAttempts(lessonId: number, minutes: number) {
  return http.post<{ updated: number }>(`/teacher/lessons/${lessonId}/auto-homework/add-time`, { minutes }).then((r) => r.data);
}

export function createHomeworkTask(lessonId: number, body: { type: HwTaskType; prompt: string; data: HwTaskData; points: number }) {
  return http.post<HwTask>(`/teacher/lessons/${lessonId}/auto-homework/tasks`, body).then((r) => r.data);
}

export function updateHomeworkTask(taskId: number, body: { prompt: string; data: HwTaskData; points: number }) {
  return http.put<HwTask>(`/teacher/auto-homework/tasks/${taskId}`, body).then((r) => r.data);
}

export function deleteHomeworkTask(taskId: number) {
  return http.delete(`/teacher/auto-homework/tasks/${taskId}`);
}

export function duplicateHomeworkTask(taskId: number) {
  return http.post<HwTask>(`/teacher/auto-homework/tasks/${taskId}/duplicate`).then((r) => r.data);
}

export function reorderHomeworkTasks(lessonId: number, taskIds: number[]) {
  return http.put<HwTask[]>(`/teacher/lessons/${lessonId}/auto-homework/order`, { task_ids: taskIds }).then((r) => r.data);
}

// ── Teacher: results ──

export function getHomeworkResults(lessonId: number) {
  return http.get<HwResults>(`/teacher/lessons/${lessonId}/auto-homework/results`).then((r) => r.data);
}

export function getHomeworkProblems(lessonId: number) {
  return http.get<{ items: HwProblem[] }>(`/teacher/lessons/${lessonId}/auto-homework/problems`).then((r) => r.data.items);
}

export function getHomeworkStudent(lessonId: number, studentId: number) {
  return http.get<HwStudentDetail>(`/teacher/lessons/${lessonId}/auto-homework/students/${studentId}`).then((r) => r.data);
}

export function gradeManualTask(lessonId: number, studentId: number, body: { task_id: number; earned?: number; criteria?: string[] }) {
  return http.post(`/teacher/lessons/${lessonId}/auto-homework/students/${studentId}/manual`, body).then((r) => r.data);
}

export type HwDecisionAction = "keep" | "zero" | "edit" | "retake" | "undo";

export function decideHomework(lessonId: number, studentId: number, body: { action: HwDecisionAction; grade?: number; comment?: string }) {
  return http.post(`/teacher/lessons/${lessonId}/auto-homework/students/${studentId}/decision`, body).then((r) => r.data);
}

export function extendHomework(lessonId: number, studentId: number, until: string | null) {
  return http.post(`/teacher/lessons/${lessonId}/auto-homework/students/${studentId}/extension`, { until }).then((r) => r.data);
}

/** A handed-in file as a blob: URL (the request needs the auth header, so
 * a plain <img src> to the API can't work). The caller revokes it. */
export async function fetchHomeworkTaskFile(attemptId: number, taskId: number, asTeacher: boolean): Promise<string> {
  const path = asTeacher
    ? `/teacher/auto-homework/attempts/${attemptId}/files/${taskId}`
    : `/auto-homework/attempts/${attemptId}/files/${taskId}`;
  const r = await http.get<Blob>(path, { responseType: "blob" });
  return URL.createObjectURL(r.data);
}

// ── Student ──

export function getHomeworkState(lessonId: number) {
  return http.get<HwState>(`/lessons/${lessonId}/auto-homework`).then((r) => r.data);
}

export function startHomework(lessonId: number) {
  return http.post<HwAttempt>(`/lessons/${lessonId}/auto-homework/start`).then((r) => r.data);
}

export function saveHomeworkAnswers(attemptId: number, answers: HwAnswers, awayCount: number) {
  return http
    .put<{ saved_at: string; expires_at: string | null; server_now: string }>(`/auto-homework/attempts/${attemptId}/answers`, {
      answers,
      away_count: awayCount,
    })
    .then((r) => r.data);
}

export function uploadHomeworkFile(attemptId: number, taskId: number, file: File) {
  const form = new FormData();
  form.append("file", file);
  return http
    .post<{ file_name: string; file_kind: string | null }>(`/auto-homework/attempts/${attemptId}/files/${taskId}`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    .then((r) => r.data);
}

export function submitHomeworkAttempt(attemptId: number, answers: HwAnswers, awayCount: number) {
  return http.post<HwState>(`/auto-homework/attempts/${attemptId}/submit`, { answers, away_count: awayCount }).then((r) => r.data);
}

export function practiceHomework(lessonId: number, answers: HwAnswers) {
  return http
    .post<{ results: Record<string, { correct: boolean; earned: number; max: number }> }>(`/lessons/${lessonId}/auto-homework/practice`, {
      answers,
    })
    .then((r) => r.data.results);
}
