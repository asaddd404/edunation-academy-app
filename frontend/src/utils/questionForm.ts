import type { QuestionSavePayload, QuestionTeacher, QuestionType, RenderableQuestion } from "@/types";

/**
 * The teacher's question editor, as plain data: the form shape, the
 * conversions to and from the API, the validation the server will apply
 * (said in words, before the teacher presses save), and the student-side
 * preview of what is being built.
 */

export const QTYPE_LABEL: Record<QuestionType, string> = {
  single: "Один ответ",
  multiple: "Несколько ответов",
  matching: "Сопоставление",
  short_answer: "Ввод текста",
};

export const QTYPE_HINT: Record<QuestionType, string> = {
  single: "Ровно один верный вариант",
  multiple: "Два и больше верных · 2 балла, частичный зачёт",
  matching: "Пары «слева → справа» · 2 балла, частичный зачёт",
  short_answer: "Ученик вводит ответ, регистр и пробелы не важны",
};

// Mirror app/schemas/question.py and the column sizes in app/models/question.py.
export const LIMITS = {
  text: 1000,
  choice: 500,
  pair: 300,
  variant: 300,
  singleChoices: { min: 2, max: 6 },
  multipleChoices: { min: 2, max: 8 },
  pairs: { min: 2, max: 20 },
} as const;

let nextKey = 0;
/** Stable v-for keys, so removing row 2 does not shift focus into row 3. */
const key = () => ++nextKey;

export interface ChoiceRow {
  key: number;
  text: string;
  isCorrect: boolean;
}
export interface PairRow {
  key: number;
  promptText: string;
  answerText: string;
}
export interface VariantRow {
  key: number;
  text: string;
}

export interface QuestionForm {
  qtype: QuestionType;
  text: string;
  maxScore: number;
  choices: ChoiceRow[];
  matchPairs: PairRow[];
  answerVariants: VariantRow[];
}

export const choiceRow = (text = "", isCorrect = false): ChoiceRow => ({ key: key(), text, isCorrect });
export const pairRow = (promptText = "", answerText = ""): PairRow => ({ key: key(), promptText, answerText });
export const variantRow = (text = ""): VariantRow => ({ key: key(), text });

export function blankForm(): QuestionForm {
  return {
    qtype: "single",
    text: "",
    maxScore: 1,
    choices: [choiceRow("", true), choiceRow(), choiceRow()],
    matchPairs: [pairRow(), pairRow(), pairRow()],
    answerVariants: [variantRow()],
  };
}

export function formFromQuestion(question: QuestionTeacher): QuestionForm {
  const blank = blankForm();
  return {
    qtype: question.qtype,
    text: question.text,
    maxScore: question.max_score,
    // The other types' rows keep their blanks, so switching type while
    // editing starts from an empty set instead of nothing.
    choices: question.choices.length ? question.choices.map((c) => choiceRow(c.text, c.is_correct)) : blank.choices,
    matchPairs: question.match_pairs.length
      ? question.match_pairs.map((p) => pairRow(p.prompt_text, p.answer_text))
      : blank.matchPairs,
    answerVariants: question.answer_variants.length
      ? question.answer_variants.map((v) => variantRow(v.text))
      : blank.answerVariants,
  };
}

/** Applies the scoring rule the server enforces for the type. */
export function setQtype(form: QuestionForm, qtype: QuestionType): void {
  const previous = form.qtype;
  form.qtype = qtype;
  // Multiple/matching are always worth 2 (partial credit needs the room);
  // leaving them drops back to 1, since a 2 there was forced, not chosen.
  if (qtype === "multiple" || qtype === "matching") form.maxScore = 2;
  else if (previous === "multiple" || previous === "matching") form.maxScore = 1;
  if (qtype === "single") {
    // Keep exactly one correct choice: the first one already marked, or the first row.
    const first = Math.max(0, form.choices.findIndex((c) => c.isCorrect));
    form.choices.forEach((c, i) => (c.isCorrect = i === first));
  }
}

export function toPayload(form: QuestionForm): QuestionSavePayload {
  const isChoice = form.qtype === "single" || form.qtype === "multiple";
  return {
    qtype: form.qtype,
    text: form.text.trim(),
    max_score: form.maxScore,
    choices: isChoice ? form.choices.map((c) => ({ text: c.text.trim(), is_correct: c.isCorrect })) : [],
    match_pairs:
      form.qtype === "matching"
        ? form.matchPairs.map((p) => ({ prompt_text: p.promptText.trim(), answer_text: p.answerText.trim() }))
        : [],
    answer_variants: form.qtype === "short_answer" ? form.answerVariants.map((v) => v.text.trim()).filter(Boolean) : [],
  };
}

/** Everything that would make the server refuse the question, in words --
 * plus duplicate right-hand matching answers, which the server accepts but
 * a student could not tell apart. */
export function validate(form: QuestionForm): string[] {
  const problems: string[] = [];
  if (!form.text.trim()) problems.push("Введите текст вопроса");
  if (form.text.length > LIMITS.text) problems.push(`Текст вопроса длиннее ${LIMITS.text} символов`);

  if (form.qtype === "single" || form.qtype === "multiple") {
    const bounds = form.qtype === "single" ? LIMITS.singleChoices : LIMITS.multipleChoices;
    const correct = form.choices.filter((c) => c.isCorrect).length;
    if (form.choices.length < bounds.min || form.choices.length > bounds.max) {
      problems.push(`Нужно от ${bounds.min} до ${bounds.max} вариантов`);
    }
    if (form.choices.some((c) => !c.text.trim())) problems.push("Заполните все варианты или удалите пустые");
    if (form.choices.some((c) => c.text.length > LIMITS.choice)) {
      problems.push(`Вариант длиннее ${LIMITS.choice} символов`);
    }
    if (form.qtype === "single" && correct !== 1) problems.push("Отметьте ровно один верный вариант");
    if (form.qtype === "multiple" && correct < 2) problems.push("Отметьте минимум два верных варианта");
  } else if (form.qtype === "matching") {
    if (form.matchPairs.length < LIMITS.pairs.min) problems.push("Нужно минимум 2 пары");
    if (form.matchPairs.some((p) => !p.promptText.trim() || !p.answerText.trim())) {
      problems.push("Заполните обе стороны каждой пары или удалите пустые");
    }
    if (form.matchPairs.some((p) => p.promptText.length > LIMITS.pair || p.answerText.length > LIMITS.pair)) {
      problems.push(`Сторона пары длиннее ${LIMITS.pair} символов`);
    }
    const answers = form.matchPairs.map((p) => p.answerText.trim().toLowerCase()).filter(Boolean);
    if (new Set(answers).size !== answers.length) {
      problems.push("Правые части пар повторяются — ученик не сможет их различить");
    }
  } else {
    if (!form.answerVariants.some((v) => v.text.trim())) problems.push("Добавьте хотя бы один верный ответ");
    if (form.answerVariants.some((v) => v.text.length > LIMITS.variant)) {
      problems.push(`Ответ длиннее ${LIMITS.variant} символов`);
    }
  }
  return problems;
}

/**
 * The question as a student will receive it, for the live preview: the same
 * shape the API sends (`RenderableQuestion`), with the answer side of a
 * matching question shuffled the way the server shuffles it. Ids are
 * positions -- the preview never talks to the server.
 */
export function toPreview(form: QuestionForm): RenderableQuestion {
  const answers = form.matchPairs.map((p, i) => ({ id: `preview-${i}`, text: p.answerText || "…" }));
  // A fixed rotation rather than Math.random, so the preview does not
  // reshuffle on every keystroke.
  const rotated = answers.length > 1 ? [...answers.slice(1), answers[0]] : answers;
  return {
    id: 0,
    qtype: form.qtype,
    choices: form.choices.map((c, i) => ({ id: i, text: c.text || "…" })),
    match_prompts: form.matchPairs.map((p, i) => ({ id: i, text: p.promptText || "…" })),
    match_answers: rotated,
  };
}
