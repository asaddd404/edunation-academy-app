export interface TodayLessonRef {
  lesson_id: number;
  title: string;
  course_id: number;
  course: string;
}

export interface TodayCount extends TodayLessonRef {
  count: number;
}

export interface TodayDeadline extends TodayLessonRef {
  deadline: string;
  is_today: boolean;
  passed: boolean;
  students: number;
  not_submitted: number;
  missing_names: string[];
}

export interface TodayProblem extends TodayLessonRef {
  task_number: number;
  task_type: string;
  prompt: string;
  item_label: string | null;
  percent: number;
  total: number;
  wrong: number;
  common_wrong: string | null;
}

export interface TodayCourse {
  id: number;
  name: string;
  lessons: number;
  with_homework: number;
}

export interface TeacherToday {
  now: string;
  applications: number;
  old_homework_to_check: number;
  new_results: { total: number; lessons: TodayCount[] };
  manual_pending: { total: number; lessons: TodayCount[] };
  flagged: { total: number; lessons: TodayCount[] };
  deadlines: TodayDeadline[];
  without_homework: { total: number; lessons: TodayLessonRef[] };
  problems: TodayProblem[];
  courses: TodayCourse[];
}
