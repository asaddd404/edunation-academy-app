/** Auto-checked homework (backend: app/api/v1/homework_auto.py). */

export type HwTaskType = "gaps" | "single" | "multi" | "short" | "match" | "tf" | "order" | "essay" | "file";

export interface HwOption {
  id?: string;
  text: string;
  correct?: boolean;
}
export interface HwPair {
  id?: string;
  rid?: string;
  left: string;
  right: string;
}
export interface HwItem {
  id?: string;
  text: string;
}
export interface HwCriterion {
  id?: string;
  text: string;
  points: number;
}

/** Teacher-side task data, per type (see app/core/homework_tasks.py). */
export interface HwTaskData {
  text?: string;
  allow_typo?: boolean;
  case_sensitive?: boolean;
  options?: HwOption[];
  shuffle?: boolean;
  partial?: boolean;
  answers?: string[];
  pairs?: HwPair[];
  correct?: boolean;
  items?: HwItem[];
  min_words?: number;
  criteria?: HwCriterion[];
}

export interface HwTask {
  id: number;
  type: HwTaskType;
  prompt: string;
  data: HwTaskData;
  points: number;
  order_index: number;
  auto: boolean;
}

export interface HwSettings {
  opens_at: string | null;
  deadline: string | null;
  time_limit_minutes: number | null;
  max_attempts: number | null;
  tasks_per_student: number | null;
}

export interface HwTeacherHomework {
  settings: HwSettings;
  tasks: HwTask[];
}

// ── Student side ──

export type HwSegment = { t: string } | { gap: number };

export interface HwTaskView {
  id: number;
  type: HwTaskType;
  prompt: string;
  points: number;
  segments?: HwSegment[];
  gap_count?: number;
  options?: { id: string; text: string }[];
  lefts?: { id: string; text: string }[];
  rights?: { id: string; text: string }[];
  items?: { id: string; text: string }[];
  min_words?: number;
  criteria?: { text: string; points: number }[];
}

/** Answers keyed by task id (as a string), shape per type. */
export type HwAnswer = {
  gaps?: string[];
  option?: string;
  options?: string[];
  text?: string;
  pairs?: Record<string, string>;
  value?: boolean;
  order?: string[];
  file_name?: string;
};
export type HwAnswers = Record<string, HwAnswer>;

export interface HwAttempt {
  id: number;
  started_at: string;
  expires_at: string | null;
  tasks: HwTaskView[];
  answers: HwAnswers;
  server_now: string;
}

export interface HwResultSummary {
  attempt_id: number;
  auto_earned: number | null;
  auto_max: number | null;
  manual_max: number;
  manual_earned: number | null;
  manual_pending: boolean;
  grade: number | null;
  computed_grade: number | null;
  overridden: boolean;
}

export interface HwReviewItem {
  key: string;
  label: string;
  correct: boolean | null;
  given: string;
  words?: number;
}

export interface HwReviewBlock {
  task: HwTaskView;
  answer: HwAnswer;
  correct: {
    gaps?: string[][];
    options?: string[];
    answers?: string[];
    pairs?: Record<string, string>;
    value?: boolean;
    order?: string[];
  };
  items: HwReviewItem[];
  earned: number | null;
  max: number;
}

export interface HwState {
  has_homework: boolean;
  phase: "not_open" | "open" | "closed";
  reason: string | null;
  opens_at: string | null;
  deadline: string | null;
  time_limit_minutes: number | null;
  max_attempts: number | null;
  attempts_used: number;
  attempts_left: number | null;
  can_start: boolean;
  open_attempt: { id: number; expires_at: string | null } | null;
  task_count: number;
  has_manual: boolean;
  result: HwResultSummary | null;
  teacher_comment: string | null;
  decision: string | null;
  reveal: boolean;
  reveal_at: string | null;
  review: HwReviewBlock[] | null;
  server_now: string;
  late?: boolean;
}

// ── Teacher results ──

export interface HwResultRow {
  student: { id: number; name: string; phone: string };
  state: "not_started" | "in_progress" | "manual_pending" | "done";
  attempts_used: number;
  in_progress: boolean;
  result: HwResultSummary | null;
  duration_seconds: number | null;
  away_count: number;
  extended_until: string | null;
  decision: "keep" | "zero" | "edit" | "retake" | null;
  teacher_comment: string | null;
  flags: string[];
}

export interface HwResults {
  lesson: { id: number; title: string };
  settings: HwSettings;
  reveal_at: string | null;
  summary: {
    students: number;
    submitted: number;
    not_submitted: number;
    manual_pending: number;
    flagged: number;
    average_grade: number | null;
  };
  rows: HwResultRow[];
}

export interface HwProblem {
  task_id: number;
  task_number: number;
  task_type: HwTaskType;
  prompt: string;
  item_label: string | null;
  total: number;
  wrong: number;
  percent: number;
  common_wrong: string | null;
  common_wrong_count: number;
  students: string[];
  correct: HwReviewBlock["correct"];
}

export interface HwStudentDetailBlock extends HwReviewBlock {
  task_full: HwTask;
  manual?: { earned: number; criteria: string[]; attempt_id: number } | null;
  has_file?: boolean;
}

export interface HwStudentDetail {
  student: { id: number; name: string; phone: string };
  result: HwResultSummary | null;
  record: {
    extended_until: string | null;
    decision: string | null;
    override_grade: number | null;
    teacher_comment: string | null;
    can_undo_retake: boolean;
  };
  attempts: {
    id: number;
    status: string;
    counted: boolean;
    started_at: string;
    submitted_at: string | null;
    auto_earned: number | null;
    auto_max: number | null;
    duration_seconds: number | null;
    away_count: number;
  }[];
  latest_attempt_id: number | null;
  best_attempt_id: number | null;
  latest: HwStudentDetailBlock[] | null;
  best: HwStudentDetailBlock[] | null;
}
