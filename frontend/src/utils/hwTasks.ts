import type { HwTaskData, HwTaskType } from "@/types/autoHomework";

/** What each task type is called and does, in the teacher's words. */
export const HW_TYPES: Record<HwTaskType, { label: string; desc: string; auto: boolean; points: number }> = {
  gaps: { label: "Заполните пропуски", desc: "Текст, в котором нужно вписать слова", auto: true, points: 2 },
  single: { label: "Выбор одного ответа", desc: "А, Б, В, Г — один верный", auto: true, points: 1 },
  multi: { label: "Несколько верных", desc: "Отметить все правильные", auto: true, points: 2 },
  short: { label: "Краткий ответ", desc: "Ученик пишет число или слово", auto: true, points: 1 },
  match: { label: "Сопоставление", desc: "Соединить пары: даты и события", auto: true, points: 2 },
  tf: { label: "Верно / неверно", desc: "Согласиться с утверждением или нет", auto: true, points: 1 },
  order: { label: "Расставить по порядку", desc: "Шаги, события, даты", auto: true, points: 2 },
  essay: { label: "Развёрнутый ответ / эссе", desc: "Свободный текст, проверяете вы", auto: false, points: 10 },
  file: { label: "Фото или файл", desc: "Решение в тетради, проект — проверяете вы", auto: false, points: 5 },
};

export const HW_TYPE_ORDER: HwTaskType[] = ["gaps", "single", "multi", "short", "match", "tf", "order", "essay", "file"];

/** A new task's starting content: shaped right, but blank, so it isn't
 * saved until the teacher has filled it in. */
export function blankTask(type: HwTaskType): { prompt: string; data: HwTaskData; points: number } {
  const points = HW_TYPES[type].points;
  switch (type) {
    case "gaps":
      return { prompt: "Вставьте пропущенные слова", data: { text: "", allow_typo: false, case_sensitive: false }, points };
    case "single":
      return { prompt: "", data: { options: [{ text: "", correct: true }, { text: "" }, { text: "" }], shuffle: true }, points };
    case "multi":
      return { prompt: "", data: { options: [{ text: "", correct: true }, { text: "" }, { text: "" }], shuffle: true, partial: true }, points };
    case "short":
      return { prompt: "", data: { answers: [""], allow_typo: false, case_sensitive: false }, points };
    case "match":
      return { prompt: "Соедините пары", data: { pairs: [{ left: "", right: "" }, { left: "", right: "" }] }, points };
    case "tf":
      return { prompt: "", data: { correct: true }, points };
    case "order":
      return { prompt: "Расставьте по порядку", data: { items: [{ text: "" }, { text: "" }, { text: "" }] }, points };
    case "essay":
      return { prompt: "", data: { min_words: 0, criteria: [] }, points };
    case "file":
      return { prompt: "", data: {}, points };
  }
}

export function pluralPoints(n: number): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return "балл";
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return "балла";
  return "баллов";
}

export function formatPoints(n: number | null | undefined): string {
  if (n == null) return "—";
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(".", ",");
}

// ── Kazakhstan time (UTC+5, no daylight saving since 2024) ────────────────
// Fixed offset on purpose: a browser with older time-zone data still shows
// Asia/Almaty as UTC+6, which would move every deadline by an hour.

const KZ_OFFSET_MS = 5 * 3600_000;
const KZ_ZONE = "Etc/GMT-5"; // POSIX sign: GMT-5 means UTC+5

export function toKzParts(iso: string | null): { date: string; time: string } {
  if (!iso) return { date: "", time: "" };
  const shifted = new Date(new Date(iso).getTime() + KZ_OFFSET_MS);
  const pad = (n: number) => String(n).padStart(2, "0");
  return {
    date: `${shifted.getUTCFullYear()}-${pad(shifted.getUTCMonth() + 1)}-${pad(shifted.getUTCDate())}`,
    time: `${pad(shifted.getUTCHours())}:${pad(shifted.getUTCMinutes())}`,
  };
}

/** "" when the date is missing; the time defaults to the end of the day. */
export function fromKzParts(date: string, time: string): string | null {
  if (!date) return null;
  return `${date}T${time || "23:59"}:00+05:00`;
}

const KZ_DATE_TIME = new Intl.DateTimeFormat("ru-RU", { timeZone: KZ_ZONE, day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
const KZ_DATE = new Intl.DateTimeFormat("ru-RU", { timeZone: KZ_ZONE, day: "numeric", month: "long" });

export function formatKz(iso: string | null | undefined, withTime = true): string {
  if (!iso) return "";
  return (withTime ? KZ_DATE_TIME : KZ_DATE).format(new Date(iso));
}

/** "2 дн 5 ч", "3 ч 10 мин", "4 мин" -- for countdowns. */
export function humanLeft(ms: number): string {
  if (ms <= 0) return "0 мин";
  const minutes = Math.floor(ms / 60_000);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;
  if (days > 0) return `${days} дн ${hours} ч`;
  if (hours > 0) return `${hours} ч ${mins} мин`;
  return `${Math.max(1, mins)} мин`;
}

export function clockLeft(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

// ── Fill-the-gaps template ─────────────────────────────────────────────────
// Mirrors app/core/homework_tasks.parse_gap_template, so the editor can show
// the student's view and refuse broken brackets before the server does.

export type GapSegment = { t: string } | { gap: number; answers: string[] };

export function parseGapTemplate(text: string): { segments: GapSegment[]; error: string | null } {
  const segments: GapSegment[] = [];
  let buf = "";
  let gaps = 0;
  const flush = () => {
    if (buf) segments.push({ t: buf });
    buf = "";
  };
  for (let i = 0; i < text.length; ) {
    const c = text[i];
    if (c === "\\" && (text[i + 1] === "[" || text[i + 1] === "]")) {
      buf += text[i + 1];
      i += 2;
      continue;
    }
    if (c === "]") return { segments, error: "Есть лишняя «]» без пары «[»." };
    if (c === "[") {
      let j = i + 1;
      while (j < text.length && text[j] !== "[" && text[j] !== "]") j++;
      if (j >= text.length) return { segments, error: "Скобка «[» не закрыта." };
      if (text[j] === "[") return { segments, error: "Пропуск внутри пропуска не поддерживается." };
      const variants = text.slice(i + 1, j).split("|").map((v) => v.trim());
      if (!variants.some(Boolean)) return { segments, error: `Пропуск ${gaps + 1} пустой.` };
      if (!variants.every(Boolean)) return { segments, error: `В пропуске ${gaps + 1} есть пустой вариант.` };
      flush();
      segments.push({ gap: gaps, answers: variants });
      gaps += 1;
      i = j + 1;
      continue;
    }
    buf += c;
    i += 1;
  }
  flush();
  return { segments, error: null };
}

const escapeText = (t: string) => t.replace(/\[/g, "\\[").replace(/\]/g, "\\]");

export function serializeGapTemplate(segments: GapSegment[]): string {
  return segments.map((s) => ("t" in s ? escapeText(s.t) : `[${s.answers.join("|")}]`)).join("");
}

/** Words and the bits between them, so each word can be a button. */
const TOKEN = /([\p{L}\p{N}][\p{L}\p{N}'’\-.,]*[\p{L}\p{N}]|[\p{L}\p{N}])|([^\p{L}\p{N}]+)/gu;

export function tokenize(text: string): { text: string; word: boolean }[] {
  const out: { text: string; word: boolean }[] = [];
  for (const m of text.matchAll(TOKEN)) out.push({ text: m[0], word: m[1] !== undefined });
  return out;
}

/** Turns word `tokenIndex` of text segment `segIndex` into a gap. */
export function makeGap(segments: GapSegment[], segIndex: number, tokenIndex: number): GapSegment[] {
  const seg = segments[segIndex];
  if (!seg || !("t" in seg)) return segments;
  const tokens = tokenize(seg.t);
  const word = tokens[tokenIndex];
  if (!word?.word) return segments;
  const before = tokens.slice(0, tokenIndex).map((t) => t.text).join("");
  const after = tokens.slice(tokenIndex + 1).map((t) => t.text).join("");
  const replacement: GapSegment[] = [];
  if (before) replacement.push({ t: before });
  replacement.push({ gap: -1, answers: [word.text] });
  if (after) replacement.push({ t: after });
  return renumber([...segments.slice(0, segIndex), ...replacement, ...segments.slice(segIndex + 1)]);
}

/** Turns a gap back into plain text (its first answer). */
export function removeGap(segments: GapSegment[], segIndex: number): GapSegment[] {
  const seg = segments[segIndex];
  if (!seg || "t" in seg) return segments;
  return renumber([...segments.slice(0, segIndex), { t: seg.answers[0] }, ...segments.slice(segIndex + 1)]);
}

export function setGapAnswers(segments: GapSegment[], segIndex: number, answers: string[]): GapSegment[] {
  return segments.map((s, i) => (i === segIndex && !("t" in s) ? { gap: s.gap, answers } : s));
}

function renumber(segments: GapSegment[]): GapSegment[] {
  // Merge neighbouring text pieces and number the gaps 0..n-1 again.
  const merged: GapSegment[] = [];
  let n = 0;
  for (const s of segments) {
    const last = merged[merged.length - 1];
    if ("t" in s) {
      if (last && "t" in last) last.t += s.t;
      else merged.push({ t: s.t });
    } else {
      merged.push({ gap: n++, answers: s.answers });
    }
  }
  return merged;
}

/** Words in an essay, counted the way the server counts them. */
export function wordCount(text: string | undefined): number {
  return (text ?? "").match(/[\p{L}\p{N}_'-]+/gu)?.length ?? 0;
}

/** What still stops a task from being saved, in the teacher's words; null
 * when it's complete. The server checks again -- this just answers sooner
 * and without a request per keystroke. */
export function taskProblem(type: HwTaskType, prompt: string, data: HwTaskData): string | null {
  const blank = (s: string | undefined) => !s || !s.trim();
  if (type !== "gaps" && blank(prompt)) return type === "tf" ? "Напишите утверждение." : "Напишите вопрос или задание.";
  switch (type) {
    case "gaps": {
      if (blank(data.text)) return "Вставьте текст задания.";
      const { segments, error } = parseGapTemplate(data.text ?? "");
      if (error) return error;
      if (!segments.some((s) => "gap" in s)) return "Нажмите на слово в тексте, чтобы сделать его пропуском.";
      return null;
    }
    case "single":
    case "multi": {
      const options = data.options ?? [];
      if (options.length < 2) return "Нужно хотя бы 2 варианта ответа.";
      const empty = options.findIndex((o) => blank(o.text));
      if (empty >= 0) return `Заполните вариант ${empty + 1} или удалите его.`;
      const correct = options.filter((o) => o.correct).length;
      if (type === "single" && correct !== 1) return "Отметьте один правильный вариант.";
      if (type === "multi" && correct === 0) return "Отметьте хотя бы один правильный вариант.";
      return null;
    }
    case "short":
      return (data.answers ?? []).some((a) => !blank(a)) ? null : "Впишите правильный ответ.";
    case "match": {
      const pairs = data.pairs ?? [];
      if (pairs.length < 2) return "Нужно хотя бы 2 пары.";
      const empty = pairs.findIndex((p) => blank(p.left) || blank(p.right));
      if (empty >= 0) return `Заполните обе части пары ${empty + 1} или удалите её.`;
      const rights = pairs.map((p) => p.right.trim().toLowerCase());
      if (new Set(rights).size !== rights.length) return "Правые части пар не должны повторяться.";
      return null;
    }
    case "order": {
      const items = data.items ?? [];
      if (items.length < 2) return "Нужно хотя бы 2 пункта.";
      const empty = items.findIndex((i) => blank(i.text));
      return empty >= 0 ? `Заполните пункт ${empty + 1} или удалите его.` : null;
    }
    case "essay": {
      const empty = (data.criteria ?? []).findIndex((c) => blank(c.text));
      return empty >= 0 ? `Заполните критерий ${empty + 1} или удалите его.` : null;
    }
    default:
      return null;
  }
}

/** Mirrors app/core/homework_tasks.is_answered, for "N left unanswered". */
export function isAnswered(type: HwTaskType, a: import("@/types/autoHomework").HwAnswer | undefined): boolean {
  if (!a) return false;
  switch (type) {
    case "gaps":
      return (a.gaps ?? []).some((g) => g && g.trim());
    case "single":
      return typeof a.option === "string";
    case "multi":
      return (a.options ?? []).length > 0;
    case "short":
    case "essay":
      return !!a.text && !!a.text.trim();
    case "match":
      return Object.keys(a.pairs ?? {}).length > 0;
    case "tf":
      return typeof a.value === "boolean";
    case "order":
      return (a.order ?? []).length > 0;
    case "file":
      return !!a.file_name;
  }
}
