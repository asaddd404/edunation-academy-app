/**
 * Reading a whole variant's answer key out of one pasted string.
 *
 * The ЕНТ papers teachers import carry no answers at all — not one
 * `Жауабы:` line in two thousand questions — so every key is typed in
 * afterwards. Done card by card that is two thousand clicks and the import
 * is not worth doing; done by pasting the forty answers a variant's key is
 * printed as, it is a minute per variant. This module is the difference,
 * which is why it accepts whatever shape the key was written in rather
 * than making the teacher reformat it:
 *
 *     1-B, 2-C, 3-A          1) B 2) C 3) A          1.B 2.C 3.A
 *     1 B                    B C A D                 39: 1-A, 2-B
 *     1-BC (multiple)        В, С (Cyrillic)         across several lines
 *
 * Nothing here touches the questions. It returns what it read and what it
 * could not, so the caller can show the teacher the outcome *before*
 * anything is applied — the one guard that makes a bulk edit safe.
 */

/** Latin A–H, the labels the parser canonicalizes every option to. */
const LETTERS = "ABCDEFGH";

/**
 * Cyrillic and Kazakh letters a teacher's keyboard produces when they mean
 * a Latin label. Only the ones drawn identically to their Latin twin are
 * here: "В" is the letter on the page in a Russian paper and the letter the
 * teacher will type, and reading it as the *third* option (its position in
 * the Cyrillic alphabet) would silently mark the wrong answer correct.
 */
const HOMOGLYPHS: Record<string, string> = {
  А: "A", В: "B", С: "C", Е: "E", Н: "H", К: "K", М: "M", О: "O", Р: "P", Т: "T", Х: "X",
  Ә: "A", Ғ: "G", Қ: "K", Ң: "N", Ө: "O", Ұ: "U", Ү: "U", Һ: "H",
  // Cyrillic letters with no Latin lookalike, read by their position in a
  // paper labelled "А) Б) В) Г)". Only these two are listed: they are the
  // ones whose two possible readings agree. "Д" is deliberately absent —
  // by position it is the fifth option (E), by typing habit it is D, and
  // there is no way to tell which was meant. An unreadable "1-Д" the
  // teacher can correct beats a silent E marked correct.
  Б: "B", Г: "D",
};

export interface KeyPair {
  /** The prompt's number within the matching question. */
  left: string;
  /** The option label it pairs with. */
  right: string;
}

export interface KeyAssignment {
  questionNumber: number;
  /** Canonical option labels, in the order written. */
  letters: string[];
  /** Set for the `39: 1-A, 2-B` form only. */
  pairs?: KeyPair[];
}

export interface ParsedAnswerKey {
  assignments: KeyAssignment[];
  /** Fragments of the input that could not be read as a key at all. */
  unreadable: string[];
  /** True when the key was letters only, so it was matched by position. */
  positional: boolean;
}

export interface KeyApplyPlan {
  /** Assignments whose question number exists in the variant. */
  matched: KeyAssignment[];
  /** Question numbers named in the key that the variant does not have. */
  unknownNumbers: number[];
  /** Question numbers in the variant the key said nothing about. */
  missingNumbers: number[];
  unreadable: string[];
  positional: boolean;
}

/** The Latin label a written letter stands for, or null. */
export function canonicalLetter(letter: string): string | null {
  const upper = letter.toUpperCase();
  if (LETTERS.includes(upper)) return upper;
  const mapped = HOMOGLYPHS[upper];
  return mapped && LETTERS.includes(mapped) ? mapped : null;
}

/**
 * Exactly the glyphs that can *be* an option label — Latin A–H plus the
 * Cyrillic letters that map into that range.
 *
 * Built from the map rather than written as a range, and this is
 * load-bearing: a class of "А-Я" matches every letter of the Russian
 * alphabet, so "Не удалось найти ответы" reads as a valid letters-only key
 * and silently marks twelve wrong answers correct. The class has to be the
 * label alphabet, not the language's.
 */
const LETTER_CLASS = [
  ...LETTERS,
  ...Object.entries(HOMOGLYPHS)
    .filter(([, latin]) => LETTERS.includes(latin))
    .map(([cyrillic]) => cyrillic),
].join("");
// "39: 1-A, 2-B" -- a matching question, whose key is itself a list of
// pairs. Recognized per line and before anything else, because its inner
// "1-A" is indistinguishable from a plain "question 1 is A" once the
// leading "39:" has been read past.
const MATCHING_LINE_RE = new RegExp(`^\\s*(\\d{1,3})\\s*:\\s*((?:\\d{1,3}\\s*[-–—:]\\s*[${LETTER_CLASS}]\\b[\\s,;]*)+)$`, "i");
const PAIR_RE = new RegExp(`(\\d{1,3})\\s*[-–—:]\\s*([${LETTER_CLASS}])`, "gi");
// "1-B", "1) B", "1.B", "1: B", "1 B", and the run-together "1-BC" that a
// multiple-choice answer is written as.
const NUMBERED_RE = new RegExp(`(\\d{1,3})\\s*[-–—.):=]?\\s*([${LETTER_CLASS}](?:\\s*[,/]?\\s*[${LETTER_CLASS}])*)(?![\\wа-яё])`, "gi");
const LETTERS_ONLY_RE = new RegExp(`[${LETTER_CLASS}]`, "gi");
// The whole input is letters and separators -- the shape that licenses
// reading a key by position. Anchored, so prose never qualifies.
const SEPARATORS = `\\s,;./\\-–—`;
const LETTERS_ONLY_INPUT_RE = new RegExp(
  `^[${SEPARATORS}]*(?:[${LETTER_CLASS}][${SEPARATORS}]*)+$`,
  "i",
);

function lettersOf(chunk: string): string[] {
  const found: string[] = [];
  for (const raw of chunk.match(LETTERS_ONLY_RE) ?? []) {
    const letter = canonicalLetter(raw);
    // An unmappable glyph ends the run rather than being skipped: "1-BЯ" is
    // a typo worth surfacing, not the answer B with something ignored.
    if (!letter) return [];
    if (!found.includes(letter)) found.push(letter);
  }
  return found;
}

/**
 * Reads a pasted key.
 *
 * `questionNumbers` is used only by the letters-only form ("B C A D"),
 * which carries no numbers of its own and is therefore matched to the
 * variant's questions by position.
 */
export function parseAnswerKey(input: string, questionNumbers: number[] = []): ParsedAnswerKey {
  const assignments: KeyAssignment[] = [];
  const unreadable: string[] = [];
  const flat: string[] = [];

  for (const line of input.split(/[\n\r]+/)) {
    if (!line.trim()) continue;
    const matching = MATCHING_LINE_RE.exec(line);
    if (matching) {
      const pairs: KeyPair[] = [];
      for (const pair of matching[2].matchAll(PAIR_RE)) {
        const right = canonicalLetter(pair[2]);
        if (right) pairs.push({ left: pair[1], right });
      }
      if (pairs.length) {
        assignments.push({ questionNumber: Number(matching[1]), letters: [], pairs });
        continue;
      }
    }
    flat.push(line);
  }

  const rest = flat.join(" ");
  const numbered = [...rest.matchAll(NUMBERED_RE)];
  if (numbered.length) {
    let consumed = 0;
    for (const match of numbered) {
      const letters = lettersOf(match[2]);
      if (!letters.length) {
        unreadable.push(match[0].trim());
        continue;
      }
      assignments.push({ questionNumber: Number(match[1]), letters });
      consumed += match[0].length;
    }
    // Whatever the numbered pattern did not touch is reported rather than
    // dropped, so a teacher who pasted half a key in another format sees
    // that half of it was ignored.
    const leftover = rest.replace(NUMBERED_RE, " ").replace(/[\s,;.]+/g, "");
    if (leftover && consumed) unreadable.push(leftover);
    return { assignments, unreadable, positional: false };
  }

  // Letters only: "B C A D" means question 1 is B, question 2 is C, ...
  // Matched against the numbers the variant actually has, so a variant
  // whose file skipped a number still lines up.
  //
  // This form is accepted only when the input is *nothing but* letters and
  // separators, because it is the one form with no structure to check
  // against: pulling the letters out of prose would read "Ответы к
  // варианту" as five answers and confidently mark them correct. A leading
  // caption is stripped first, since "Ответы: B C A D" is how a key is
  // actually pasted.
  const body = rest.replace(/^[^:]{0,40}:\s*/, "").trim();
  if (!body || !LETTERS_ONLY_INPUT_RE.test(body)) {
    if (rest.trim()) unreadable.push(rest.trim());
    return { assignments, unreadable, positional: false };
  }

  for (const [index, raw] of (body.match(LETTERS_ONLY_RE) ?? []).entries()) {
    const letter = canonicalLetter(raw);
    const questionNumber = questionNumbers[index];
    if (!letter || questionNumber === undefined) {
      unreadable.push(raw);
      continue;
    }
    assignments.push({ questionNumber, letters: [letter] });
  }
  return { assignments, unreadable, positional: assignments.length > 0 };
}

/**
 * What applying a key *would* do, computed against the variant's real
 * question numbers so the teacher can be shown the outcome first.
 *
 * A later assignment for the same question wins, which is what makes
 * pasting a corrected key over a wrong one behave the way it looks.
 */
export function planAnswerKey(input: string, questionNumbers: number[]): KeyApplyPlan {
  const { assignments, unreadable, positional } = parseAnswerKey(input, questionNumbers);
  const available = new Set(questionNumbers);

  const byNumber = new Map<number, KeyAssignment>();
  const unknownNumbers: number[] = [];
  for (const assignment of assignments) {
    if (!available.has(assignment.questionNumber)) {
      if (!unknownNumbers.includes(assignment.questionNumber)) {
        unknownNumbers.push(assignment.questionNumber);
      }
      continue;
    }
    byNumber.set(assignment.questionNumber, assignment);
  }

  return {
    matched: [...byNumber.values()].sort((a, b) => a.questionNumber - b.questionNumber),
    unknownNumbers: unknownNumbers.sort((a, b) => a - b),
    missingNumbers: questionNumbers.filter((n) => !byNumber.has(n)).sort((a, b) => a - b),
    unreadable,
    positional,
  };
}

/** "Будет проставлено: 38 из 40. Не найдены вопросы: 12, 27" */
export function describePlan(plan: KeyApplyPlan, total: number): string {
  const parts = [`Будет проставлено: ${plan.matched.length} из ${total}`];
  if (plan.missingNumbers.length) {
    const shown = plan.missingNumbers.slice(0, 12).join(", ");
    const more = plan.missingNumbers.length > 12 ? ` и ещё ${plan.missingNumbers.length - 12}` : "";
    parts.push(`Без ответа останутся: ${shown}${more}`);
  }
  if (plan.unknownNumbers.length) {
    parts.push(`Нет таких вопросов: ${plan.unknownNumbers.join(", ")}`);
  }
  if (plan.unreadable.length) {
    parts.push(`Не разобрано: ${plan.unreadable.slice(0, 6).join(" ")}`);
  }
  if (plan.positional) {
    parts.push("Ключ без номеров — ответы сопоставлены по порядку");
  }
  return parts.join(". ") + ".";
}
