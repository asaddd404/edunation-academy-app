import type { AnswerPayload, QuestionType } from "@/types";

/** Whether `answer` counts as an attempt at a question of type `qtype` --
 * the same rule for course tests and the ЕНТ simulator. */
export function isAnswered(qtype: QuestionType, answer: AnswerPayload | undefined): boolean {
  if (!answer) return false;
  switch (qtype) {
    case "single":
      return answer.choice_id != null;
    case "multiple":
      return (answer.choice_ids?.length ?? 0) > 0;
    case "matching":
      return Object.keys(answer.pairs ?? {}).length > 0;
    default:
      return (answer.text ?? "").trim().length > 0;
  }
}

/** 133 -> "02:13". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rest = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${rest}` : `${String(m).padStart(2, "0")}:${rest}`;
}
