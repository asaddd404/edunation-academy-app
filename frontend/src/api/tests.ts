import http from "@/api/http";
import type { AnswerPayload, TestAttemptResult, TestAttemptStart, TestHubCourse, TestInfo, TestKind } from "@/types";

// Lesson mini-tests and section tests share one flow: look at the test,
// start an attempt (the server draws its questions), submit that attempt.
function base(kind: TestKind, id: number): string {
  return kind === "lesson" ? `/lessons/${id}/test` : `/sections/${id}/test`;
}

export function getTestInfo(kind: TestKind, id: number) {
  return http.get<TestInfo>(base(kind, id)).then((r) => r.data);
}

export function startTestAttempt(kind: TestKind, id: number) {
  return http.post<TestAttemptStart>(`${base(kind, id)}/attempts/start`).then((r) => r.data);
}

export function submitTestAttempt(kind: TestKind, id: number, attemptId: number, answers: AnswerPayload[]) {
  return http
    .post<TestAttemptResult>(`${base(kind, id)}/attempts`, { attempt_id: attemptId, answers })
    .then((r) => r.data);
}

export function listMyTests() {
  return http.get<TestHubCourse[]>("/me/tests").then((r) => r.data);
}
