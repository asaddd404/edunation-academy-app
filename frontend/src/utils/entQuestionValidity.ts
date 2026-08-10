/**
 * Whether a question would survive `/bulk-create`, checked here rather than
 * discovered there.
 *
 * These rules mirror `EntQuestionIn._validate` on the backend, which is the
 * authority — this is a copy, and the copy exists because of what the
 * preview promises. "Сохранить готовые (104)" has to mean 104 saved: a
 * teacher who pastes a key for forty questions and is told all forty are
 * ready, then gets a list of seventeen skipped with a validation message
 * each, has been told something false at the moment it mattered.
 *
 * The cases are not hypothetical. Pasting "1-A, 2-B, …" over a variant sets
 * exactly one answer per question, which is right for the single-choice
 * items and wrong for every six-option "выберите несколько" among them; and
 * a question the file printed with one surviving option cannot be saved at
 * all, however plausible the parser's guess at its answer.
 *
 * Reported as a sentence rather than a boolean because the teacher has to
 * fix it, and "нужен ещё один правильный вариант" is a fix while "не
 * сохранится" is a riddle.
 */
import type { EntQuestionImport } from "@/types";

export function savableProblem(q: EntQuestionImport): string | null {
  const correct = q.choices.filter((c) => c.is_correct).length;

  if (q.qtype === "single") {
    if (q.choices.length < 2) return "Нужно минимум 2 варианта ответа";
    if (q.choices.length > 6) return "Не больше 6 вариантов ответа";
    if (correct !== 1) return "Должен быть отмечен ровно один правильный вариант";
    return null;
  }

  if (q.qtype === "multiple") {
    if (q.choices.length < 2) return "Нужно минимум 2 варианта ответа";
    if (q.choices.length > 8) return "Не больше 8 вариантов ответа";
    if (correct < 2) return "Нужно отметить минимум два правильных варианта";
    return null;
  }

  if (q.qtype === "matching") {
    const pairs = q.match_pairs.filter((p) => p.prompt_text && p.answer_text).length;
    if (pairs < 2) return "Нужно минимум 2 сопоставленные пары";
    return null;
  }

  if (!q.answer_variants.some((v) => v.trim())) return "Нужен хотя бы один правильный ответ";
  return null;
}

/** The score the backend insists on for a given type. */
export function requiredMaxScore(qtype: EntQuestionImport["qtype"]): number {
  return qtype === "multiple" || qtype === "matching" ? 2 : 1;
}
