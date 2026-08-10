// Shared shape between the "new question" form (TeacherEntBankView, one per
// subject) and the in-place edit form rendered inside a question card. Kept
// here rather than duplicated so the two never drift on validation rules.
import type { EntQuestionCreatePayload } from "@/api/ent";
import type { EntQuestionType, ExamLanguage } from "@/types";

export interface QuestionForm {
  qtype: EntQuestionType;
  text: string;
  language: ExamLanguage;
  maxScore: number;
  /** Newly picked file, uploaded only after the question row itself is saved. */
  imageFile: File | null;
  /** Whether the question being edited already has an image on the server. */
  hasImage: boolean;
  choices: { text: string; isCorrect: boolean }[];
  matchPairs: { promptText: string; answerText: string }[];
  answerVariants: string[];
}

export function blankQuestionForm(language: ExamLanguage): QuestionForm {
  return {
    qtype: "single",
    text: "",
    language,
    maxScore: 1,
    imageFile: null,
    hasImage: false,
    choices: [
      { text: "", isCorrect: true },
      { text: "", isCorrect: false },
    ],
    matchPairs: [
      { promptText: "", answerText: "" },
      { promptText: "", answerText: "" },
    ],
    answerVariants: [""],
  };
}

export function isQuestionFormValid(form: QuestionForm): boolean {
  if (!form.text.trim()) return false;
  if (form.qtype === "single") {
    return (
      form.choices.length >= 2 &&
      form.choices.every((c) => c.text.trim()) &&
      form.choices.filter((c) => c.isCorrect).length === 1
    );
  }
  if (form.qtype === "multiple") {
    return (
      form.choices.length >= 2 &&
      form.choices.every((c) => c.text.trim()) &&
      form.choices.filter((c) => c.isCorrect).length >= 2
    );
  }
  if (form.qtype === "matching") {
    return form.matchPairs.length >= 2 && form.matchPairs.every((p) => p.promptText.trim() && p.answerText.trim());
  }
  return form.answerVariants.some((v) => v.trim());
}

export function buildEntQuestionPayload(form: QuestionForm): EntQuestionCreatePayload {
  return {
    qtype: form.qtype,
    text: form.text,
    language: form.language,
    max_score: form.maxScore,
    choices:
      form.qtype === "single" || form.qtype === "multiple"
        ? form.choices.map((c) => ({ text: c.text, is_correct: c.isCorrect }))
        : undefined,
    match_pairs:
      form.qtype === "matching"
        ? form.matchPairs.map((p) => ({ prompt_text: p.promptText, answer_text: p.answerText }))
        : undefined,
    answer_variants: form.qtype === "short_answer" ? form.answerVariants.filter((v) => v.trim()) : undefined,
  };
}
