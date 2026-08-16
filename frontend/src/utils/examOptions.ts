/**
 * Answer options are labelled А, Б, В… the way they are on the real ЕНТ
 * answer sheet, so a student can say "выбрал В" and mean the same thing in
 * both places. Ё and Й are skipped for the same reason the exam skips them:
 * they read as decorated variants of a neighbouring letter at a glance.
 */
const OPTION_LETTERS = [
  "А", "Б", "В", "Г", "Д", "Е", "Ж", "З", "И", "К",
  "Л", "М", "Н", "О", "П", "Р", "С", "Т", "У", "Ф",
];

export function optionLetter(index: number): string {
  return OPTION_LETTERS[index] ?? String(index + 1);
}

/** Percentage for progress rings/bars, clamped and safe when max is 0. */
export function scorePercent(score: number, max: number): number {
  if (!max || max <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((score / max) * 100)));
}

/** Colour tier for a result, shared by the score ring and per-subject bars. */
export function scoreTone(percent: number): "success" | "warning" | "danger" {
  if (percent >= 70) return "success";
  if (percent >= 40) return "warning";
  return "danger";
}
