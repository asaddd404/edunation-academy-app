export type Role = "student" | "teacher" | "admin";
export type ApplicationStatus = "pending" | "approved" | "rejected";

export interface User {
  id: number;
  phone: string;
  first_name: string;
  last_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface Category {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
  my_application_status: ApplicationStatus | null;
}

export interface Application {
  id: number;
  student_id: number;
  category_id: number;
  status: ApplicationStatus;
  decided_by: number | null;
  decided_at: string | null;
  created_at: string;
  student_name: string | null;
  student_phone: string | null;
  category_name: string | null;
}

export type HomeworkStatus = "submitted" | "accepted" | "revision_requested";

export interface LessonSummary {
  id: number;
  title: string;
  order_index: number;
  is_unlocked: boolean;
  is_passed: boolean;
}

export interface Section {
  id: number;
  category_id: number;
  title: string;
  description: string | null;
  order_index: number;
  created_at: string;
  lessons: LessonSummary[];
  has_test: boolean;
  is_test_unlocked: boolean;
  is_test_passed: boolean;
}

export interface Choice {
  id: number;
  text: string;
}

export interface Question {
  id: number;
  text: string;
  order_index: number;
  choices: Choice[];
}

export interface HomeworkSubmission {
  id: number;
  lesson_id: number;
  student_id: number;
  text_answer: string | null;
  file_original_name: string | null;
  status: HomeworkStatus;
  teacher_feedback: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
  student_name: string | null;
  lesson_title: string | null;
}

export interface LessonDetail {
  id: number;
  section_id: number;
  title: string;
  description: string | null;
  video_url: string | null;
  homework_assignment: string | null;
  order_index: number;
  created_at: string;
  is_unlocked: boolean;
  is_passed: boolean;
  questions: Question[];
  my_homework: HomeworkSubmission | null;
}

export interface TestAttemptResult {
  score: number;
  passed: boolean;
  attempt_number: number;
}

export interface SectionTest {
  section_id: number;
  is_unlocked: boolean;
  is_passed: boolean;
  questions: Question[];
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface AuthResponse extends TokenPair {
  user: User;
}
