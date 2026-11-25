import http from "@/api/http";

export interface MyTest {
  kind: "lesson" | "section";
  id: number;
  title: string;
  question_count: number;
  pool_size: number;
  is_unlocked: boolean;
  is_passed: boolean;
  in_progress: boolean;
  attempts_used: number;
  best_score: number | null;
}

export interface MyTestsCourse {
  category_id: number;
  category_name: string;
  sections: { section_id: number; title: string; tests: MyTest[] }[];
}

export function listMyTests() {
  return http.get<MyTestsCourse[]>("/tests/my").then((r) => r.data);
}
