import http from "@/api/http";
import type {
  EntLeaderboard,
  EntQuestionTeacher,
  EntQuestionType,
  EntSimulation,
  EntSimulationAnswerPayload,
  EntSimulationResult,
  EntSimulationSummary,
  EntSubject,
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

export function getEntLeaderboard(limit = 20) {
  return http.get<EntLeaderboard>("/ent/leaderboard", { params: { limit } }).then((r) => r.data);
}

// Teacher/admin question bank

export function listTeacherEntSubjects() {
  return http.get<EntSubject[]>("/teacher/ent/subjects").then((r) => r.data);
}

export function createEntSubject(payload: { name: string; slug?: string }) {
  return http.post<EntSubject>("/teacher/ent/subjects", payload).then((r) => r.data);
}

export function updateEntSubject(id: number, payload: { name?: string; is_active?: boolean }) {
  return http.patch<EntSubject>(`/teacher/ent/subjects/${id}`, payload).then((r) => r.data);
}

export function listSubjectQuestions(subjectId: number) {
  return http.get<EntQuestionTeacher[]>(`/teacher/ent/subjects/${subjectId}/questions`).then((r) => r.data);
}

export interface EntQuestionCreatePayload {
  qtype: EntQuestionType;
  text: string;
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
