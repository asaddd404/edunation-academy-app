// The ru/kk vocabulary, in one place: the flag, the name of the language in
// that language, and the order the two are offered in. Three screens show
// this (import preview, question bank, exam start) and a string literal
// repeated across them is how "Қазақша" ends up spelled two ways.

import type { ExamLanguage } from "@/types";

export const EXAM_LANGUAGES: ExamLanguage[] = ["ru", "kk"];

export const LANGUAGE_FLAG: Record<ExamLanguage, string> = {
  ru: "🇷🇺",
  kk: "🇰🇿",
};

/** Each language named in itself -- a student picking "Қазақша" is reading
 * the option in the language they are about to sit the exam in. */
export const LANGUAGE_LABEL: Record<ExamLanguage, string> = {
  ru: "Русский",
  kk: "Қазақша",
};

export function languageChip(language: ExamLanguage): string {
  return `${LANGUAGE_FLAG[language]} ${LANGUAGE_LABEL[language]}`;
}

export function otherLanguage(language: ExamLanguage): ExamLanguage {
  return language === "ru" ? "kk" : "ru";
}
