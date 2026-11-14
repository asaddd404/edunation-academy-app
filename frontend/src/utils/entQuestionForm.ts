// Shared shape between the "new question" form (TeacherEntBankView, one per
// subject) and the in-place edit form rendered inside a question card. Kept
// here rather than duplicated so the two never drift on validation rules.
import type { EntQuestionCreatePayload } from "@/api/ent";
import type { EntQuestionTeacher, EntQuestionType, ExamLanguage } from "@/types";

export interface QuestionForm {
  qtype: EntQuestionType;
  text: string;
  /** The passage a "context" question is asked about. */
  contextText: string;
  language: ExamLanguage;
  maxScore: number;
  /** Newly picked file, uploaded only after the question row itself is saved. */
  imageFile: File | null;
  /** Whether the question being edited already has an image on the server. */
  hasImage: boolean;
  choices: { text: string; isCorrect: boolean }[];
  matchPairs: { promptText: string; answerText: string }[];
  /** Extra answers on the right that pair with no prompt -- so a question
   * can offer, say, 4 answers for 2 prompts. */
  matchDistractors: string[];
  answerVariants: string[];
}

// The fixed ЕНТ format of a profile subject; mirrors app/core/ent_structure.py.
export const PROFILE_SINGLE_OPTIONS = 4;
export const PROFILE_MULTIPLE_OPTIONS = 6;
export const MAX_MATCH_ROWS = 10;
export const PROFILE_STRUCTURE: { qtype: EntQuestionType; from: number; to: number; label: string }[] = [
  { qtype: "single", from: 1, to: 25, label: "один правильный ответ из 4" },
  { qtype: "context", from: 26, to: 30, label: "задания на основе текста" },
  { qtype: "matching", from: 31, to: 35, label: "сопоставление, по 2 балла" },
  { qtype: "multiple", from: 36, to: 40, label: "от 1 до 3 правильных из 6, по 2 балла" },
];

function blankChoices(count: number): QuestionForm["choices"] {
  return Array.from({ length: count }, (_, i) => ({ text: "", isCorrect: i === 0 }));
}

export function blankQuestionForm(language: ExamLanguage, profile = false): QuestionForm {
  return {
    qtype: "single",
    text: "",
    contextText: "",
    language,
    maxScore: 1,
    imageFile: null,
    hasImage: false,
    choices: blankChoices(profile ? PROFILE_SINGLE_OPTIONS : 2),
    matchPairs: [
      { promptText: "", answerText: "" },
      { promptText: "", answerText: "" },
    ],
    matchDistractors: [],
    answerVariants: [""],
  };
}

export function questionFormFrom(question: EntQuestionTeacher): QuestionForm {
  const fallback = blankQuestionForm(question.language);
  const pairs = question.match_pairs.filter((p) => p.prompt_text !== null);
  return {
    qtype: question.qtype,
    text: question.text,
    contextText: question.context_text ?? "",
    language: question.language,
    maxScore: question.max_score,
    imageFile: null,
    hasImage: question.has_image,
    choices: question.choices.length
      ? question.choices.map((c) => ({ text: c.text, isCorrect: c.is_correct }))
      : fallback.choices,
    matchPairs: pairs.length
      ? pairs.map((p) => ({ promptText: p.prompt_text ?? "", answerText: p.answer_text }))
      : fallback.matchPairs,
    matchDistractors: question.match_pairs.filter((p) => p.prompt_text === null).map((p) => p.answer_text),
    answerVariants: question.answer_variants.length ? question.answer_variants.map((v) => v.text) : [""],
  };
}

/** How many options a choice question gets in a profile subject. */
export function profileOptionCount(qtype: EntQuestionType): number | null {
  if (qtype === "single" || qtype === "context") return PROFILE_SINGLE_OPTIONS;
  if (qtype === "multiple") return PROFILE_MULTIPLE_OPTIONS;
  return null;
}

/** After a type change: the score the type requires, and in a profile subject
 * exactly as many option rows as the format has (typed text is kept). */
export function adaptToQtype(form: QuestionForm, profile: boolean): void {
  if (form.qtype === "multiple" || form.qtype === "matching") form.maxScore = 2;
  else if (profile || form.qtype === "context") form.maxScore = 1;

  const count = profile ? profileOptionCount(form.qtype) : null;
  if (count !== null) {
    while (form.choices.length < count) form.choices.push({ text: "", isCorrect: false });
    form.choices.splice(count);
  }
  if (form.qtype === "single" || form.qtype === "context") {
    // One correct answer: keep the first one marked, if any.
    const first = form.choices.findIndex((c) => c.isCorrect);
    form.choices.forEach((c, i) => (c.isCorrect = i === Math.max(first, 0)));
  }
}

/** Why the form cannot be saved, as a sentence the teacher can act on, or
 * null. Mirrors EntQuestionIn and, for a profile subject, ent_structure. */
export function questionFormProblem(form: QuestionForm, profile = false): string | null {
  if (!form.text.trim()) return "Введите текст вопроса";
  const correct = form.choices.filter((c) => c.isCorrect).length;

  if (form.qtype === "single" || form.qtype === "context") {
    if (form.qtype === "context" && !form.contextText.trim()) return "Добавьте текст, на основе которого задан вопрос";
    if (profile && form.choices.length !== PROFILE_SINGLE_OPTIONS) return `Нужно ровно ${PROFILE_SINGLE_OPTIONS} варианта`;
    if (form.choices.length < 2) return "Нужно минимум 2 варианта";
    if (!form.choices.every((c) => c.text.trim())) return "Заполните все варианты";
    if (correct !== 1) return "Отметьте один правильный вариант";
    return null;
  }
  if (form.qtype === "multiple") {
    if (profile && form.choices.length !== PROFILE_MULTIPLE_OPTIONS) return `Нужно ровно ${PROFILE_MULTIPLE_OPTIONS} вариантов`;
    if (form.choices.length < 2) return "Нужно минимум 2 варианта";
    if (!form.choices.every((c) => c.text.trim())) return "Заполните все варианты";
    if (correct < 1 || correct > 3) return "Отметьте от 1 до 3 правильных вариантов";
    return null;
  }
  if (form.qtype === "matching") {
    if (form.matchPairs.length < 2) return "Нужно минимум 2 пары";
    if (!form.matchPairs.every((p) => p.promptText.trim() && p.answerText.trim())) return "Заполните обе стороны каждой пары";
    if (!form.matchDistractors.every((d) => d.trim())) return "Заполните лишние варианты или удалите пустые";
    if (form.matchPairs.length + form.matchDistractors.length > MAX_MATCH_ROWS)
      return `Не больше ${MAX_MATCH_ROWS} вариантов ответа`;
    return null;
  }
  if (profile) return "В профильном предмете нет вопросов с кратким ответом";
  return form.answerVariants.some((v) => v.trim()) ? null : "Нужен хотя бы один правильный ответ";
}

export function isQuestionFormValid(form: QuestionForm, profile = false): boolean {
  return questionFormProblem(form, profile) === null;
}

export function buildEntQuestionPayload(form: QuestionForm): EntQuestionCreatePayload {
  const hasChoices = form.qtype === "single" || form.qtype === "context" || form.qtype === "multiple";
  return {
    qtype: form.qtype,
    text: form.text,
    context_text: form.qtype === "context" ? form.contextText : undefined,
    language: form.language,
    max_score: form.maxScore,
    choices: hasChoices ? form.choices.map((c) => ({ text: c.text, is_correct: c.isCorrect })) : undefined,
    match_pairs:
      form.qtype === "matching"
        ? [
            ...form.matchPairs.map((p) => ({ prompt_text: p.promptText, answer_text: p.answerText })),
            ...form.matchDistractors.map((d) => ({ prompt_text: null, answer_text: d })),
          ]
        : undefined,
    answer_variants: form.qtype === "short_answer" ? form.answerVariants.filter((v) => v.trim()) : undefined,
  };
}
