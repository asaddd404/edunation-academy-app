// The ru/kk vocabulary, in one place: the name of the language in that
// language, and the order the two are offered in. Three screens show this
// (import preview, question bank, exam start) and a string literal repeated
// across them is how "Қазақша" ends up spelled two ways.
//
// The flag emoji that used to live here is gone: Windows does not render
// regional-indicator pairs as flags at all -- it shows the bare letters --
// so it was never actually a flag for this app's users. Use the
// components/ui/LanguageChip.vue plate instead.

import type { ExamLanguage } from "@/types";

export const EXAM_LANGUAGES: ExamLanguage[] = ["ru", "kk"];

/** Each language named in itself -- a student picking "Қазақша" is reading
 * the option in the language they are about to sit the exam in. */
export const LANGUAGE_LABEL: Record<ExamLanguage, string> = {
  ru: "Русский",
  kk: "Қазақша",
};

export function otherLanguage(language: ExamLanguage): ExamLanguage {
  return language === "ru" ? "kk" : "ru";
}
