import http from "@/api/http";
import type {
  EntBulkCreateResult,
  EntLeaderboard,
  EntPdfImportResult,
  EntQuestionImport,
  EntQuestionTeacher,
  EntQuestionType,
  EntSimulation,
  EntSimulationAnswerPayload,
  EntSimulationResult,
  EntSimulationSummary,
  LeaderboardPeriod,
  EntSubject,
  ExamLanguage,
  Page,
} from "@/types";

// Student flow

export function listEntSubjects() {
  return http.get<EntSubject[]>("/ent/subjects").then((r) => r.data);
}

export function startEntSimulation(payload: {
  subject_ids: number[];
  questions_per_subject: number;
  is_timed: boolean;
  duration_minutes?: number;
  /** Only questions in this language are drawn. A subject that cannot fill
   * its share in it answers 422 with which subject is short and by how much. */
  language: ExamLanguage;
}) {
  return http.post<EntSimulation>("/ent/simulations", payload).then((r) => r.data);
}

export function getEntSimulation(id: number) {
  return http.get<EntSimulation>(`/ent/simulations/${id}`).then((r) => r.data);
}

export function submitEntSimulation(id: number, answers: EntSimulationAnswerPayload[]) {
  return http.post<EntSimulationResult>(`/ent/simulations/${id}/submit`, { answers }).then((r) => r.data);
}

export function getEntSimulationResult(id: number) {
  return http.get<EntSimulationResult>(`/ent/simulations/${id}/result`).then((r) => r.data);
}

export function listEntSimulations() {
  return http.get<EntSimulationSummary[]>("/ent/simulations").then((r) => r.data);
}

export function getEntLeaderboard(limit = 20, period: LeaderboardPeriod = "all") {
  return http.get<EntLeaderboard>("/ent/leaderboard", { params: { limit, period } }).then((r) => r.data);
}

// Teacher/admin question bank

export function listTeacherEntSubjects() {
  return http.get<EntSubject[]>("/teacher/ent/subjects").then((r) => r.data);
}

export function createEntSubject(payload: { name: string; slug?: string }) {
  return http.post<EntSubject>("/teacher/ent/subjects", payload).then((r) => r.data);
}

export interface EntSubjectUpdatePayload {
  name?: string;
  is_active?: boolean;
  single_choice_count?: number;
  multiple_choice_count?: number;
  matching_count?: number;
  short_answer_count?: number;
}

export function updateEntSubject(id: number, payload: EntSubjectUpdatePayload) {
  return http.patch<EntSubject>(`/teacher/ent/subjects/${id}`, payload).then((r) => r.data);
}

/** Omitting `language` returns the whole bank — the "Все" tab. */
export function listSubjectQuestions(
  subjectId: number,
  language?: ExamLanguage,
  page = 1,
  perPage = 50,
) {
  return http
    .get<Page<EntQuestionTeacher>>(`/teacher/ent/subjects/${subjectId}/questions`, {
      params: { language, page, per_page: perPage },
    })
    .then((r) => r.data);
}

export interface EntQuestionCreatePayload {
  qtype: EntQuestionType;
  text: string;
  language: ExamLanguage;
  max_score: number;
  choices?: { text: string; is_correct: boolean }[];
  match_pairs?: { prompt_text: string; answer_text: string }[];
  answer_variants?: string[];
}

export function createSubjectQuestion(subjectId: number, payload: EntQuestionCreatePayload) {
  return http.post<EntQuestionTeacher>(`/teacher/ent/subjects/${subjectId}/questions`, payload).then((r) => r.data);
}

export function updateSubjectQuestion(questionId: number, payload: EntQuestionCreatePayload) {
  return http.patch<EntQuestionTeacher>(`/teacher/ent/questions/${questionId}`, payload).then((r) => r.data);
}

export function deleteEntQuestion(questionId: number) {
  return http.delete(`/teacher/ent/questions/${questionId}`);
}

export interface EntBulkDeleteResult {
  deleted: number[];
  failed: { id: number; reason: string }[];
}

export function bulkDeleteEntQuestions(questionIds: number[]) {
  return http
    .post<EntBulkDeleteResult>("/teacher/ent/questions/bulk-delete", { question_ids: questionIds })
    .then((r) => r.data);
}

export function uploadEntQuestionImage(questionId: number, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return http.post<EntQuestionTeacher>(`/teacher/ent/questions/${questionId}/image`, formData).then((r) => r.data);
}

export function deleteEntQuestionImage(questionId: number) {
  return http.delete<EntQuestionTeacher>(`/teacher/ent/questions/${questionId}/image`).then((r) => r.data);
}

export function getEntQuestionImageUrl(questionId: number) {
  return `${import.meta.env.VITE_API_BASE_URL}/ent/questions/${questionId}/image`;
}

export function importEntQuestionsFromPdf(subjectId: number, file: File) {
  const formData = new FormData();
  formData.append("subject_id", String(subjectId));
  formData.append("file", file);
  return http.post<EntPdfImportResult>("/teacher/ent/questions/import-pdf", formData).then((r) => r.data);
}

export function bulkCreateEntQuestions(subjectId: number, questions: EntQuestionImport[]) {
  return http
    .post<EntBulkCreateResult>("/teacher/ent/questions/bulk-create", { subject_id: subjectId, questions })
    .then((r) => r.data);
}
