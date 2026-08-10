/**
 * What the PDF import's per-question flags mean to a teacher.
 *
 * The parser reports named faults rather than one "needs review" boolean,
 * because with two thousand questions on screen the useful question is not
 * *how sure* the parser is but *what it wants looked at* — and above all
 * whether the question can be saved at all. A missing answer key is twenty
 * seconds of pasting; a missing option list is a question to rebuild by
 * hand. Colouring both amber told the teacher neither.
 *
 * Flag names mirror the constants in `app/core/ent_pdf_import.py`; an
 * unknown one degrades to a neutral chip rather than disappearing, so a
 * flag added on the backend is visible here before this file catches up.
 */

export type FlagTone = "danger" | "warning" | "muted";

export interface FlagInfo {
  label: string;
  tone: FlagTone;
  /** Blocking flags stop a question being saved as ready. */
  blocking: boolean;
}

const FLAGS: Record<string, FlagInfo> = {
  // ── Blocking: the question cannot be saved as it stands ──────────────
  missing_key: { label: "Ответ не указан в файле", tone: "danger", blocking: true },
  missing_options: { label: "Варианты не распознаны", tone: "danger", blocking: true },
  matching_left_empty: { label: "Пункты сопоставления не найдены", tone: "danger", blocking: true },
  key_option_mismatch: { label: "Ключ не совпадает с вариантами", tone: "danger", blocking: true },
  // ── Advisory: worth a glance, saves fine ─────────────────────────────
  duplicate_option_label: { label: "Повторяющиеся метки вариантов", tone: "warning", blocking: false },
  options_autolabeled: { label: "Метки вариантов присвоены автоматически", tone: "warning", blocking: false },
  single_option_only: { label: "Найден только один вариант — проверьте", tone: "warning", blocking: false },
  mixed_option_types: { label: "Смешанные типы вариантов", tone: "warning", blocking: false },
  question_number_gap: { label: "Возможно, пропущен вопрос", tone: "warning", blocking: false },
  long_question_text: { label: "Длинный текст — возможен посторонний фрагмент", tone: "muted", blocking: false },
};

const UNKNOWN: FlagInfo = { label: "", tone: "muted", blocking: false };

export function flagInfo(flag: string): FlagInfo {
  // The raw name is a better label than nothing: a teacher who reports
  // "it says options_autolabeled" can be helped, one who reports "it says
  // something" cannot.
  return FLAGS[flag] ?? { ...UNKNOWN, label: flag };
}

export function isBlockingFlag(flag: string): boolean {
  return flagInfo(flag).blocking;
}

/** A question is "ready" when nothing blocks saving it. */
export function isReady(flags: string[]): boolean {
  return !flags.some(isBlockingFlag);
}

/** Every flag present in a set of questions, blocking ones first. */
export function rankFlags(flags: Iterable<string>): string[] {
  const order = (flag: string) => (isBlockingFlag(flag) ? 0 : flagInfo(flag).tone === "warning" ? 1 : 2);
  return [...new Set(flags)].sort((a, b) => order(a) - order(b) || a.localeCompare(b));
}

export const FLAG_CHIP_CLASS: Record<FlagTone, string> = {
  danger: "bg-clay/10 text-clay border-clay/30",
  warning: "bg-marigold/20 text-ink border-marigold/40",
  muted: "bg-paper-2 text-ink-3 border-line",
};
