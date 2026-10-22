import http from "@/api/http";
import type { Leaderboard, LeaderboardPeriod, LeaderboardScopeCategory, TestLeaderboard } from "@/types";

/** Overall XP board -- ЕНТ simulations and course tests together. */
export function getLeaderboard(limit = 20, period: LeaderboardPeriod = "all") {
  return http.get<Leaderboard>("/leaderboard", { params: { limit, period } }).then((r) => r.data);
}

export function getLessonLeaderboard(lessonId: number, limit = 20) {
  return http.get<TestLeaderboard>(`/leaderboard/lessons/${lessonId}`, { params: { limit } }).then((r) => r.data);
}

export function getSectionLeaderboard(sectionId: number, limit = 20) {
  return http.get<TestLeaderboard>(`/leaderboard/sections/${sectionId}`, { params: { limit } }).then((r) => r.data);
}

/** The lessons and sections, in the student's approved courses, that have a test board. */
export function listLeaderboardScopes() {
  return http.get<LeaderboardScopeCategory[]>("/leaderboard/scopes").then((r) => r.data);
}
