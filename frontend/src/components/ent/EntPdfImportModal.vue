<script setup lang="ts">
import { CircleCheck, FileText, Info, TriangleAlert, X } from "@lucide/vue";
import { computed, nextTick, reactive, ref } from "vue";

import { bulkCreateEntQuestions, importEntQuestionsFromPdf } from "@/api/ent";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import { useModalFocusTrap } from "@/composables/useModalFocusTrap";
import type {
  EntBulkCreateResult,
  EntPdfImportStats,
  EntQuestionImport,
  EntQuestionType,
  EntSubject,
  ExamLanguage,
} from "@/types";
import { describePlan, planAnswerKey, type KeyAssignment } from "@/utils/answerKey";
import { FLAG_CHIP_CLASS, flagInfo, isReady, rankFlags } from "@/utils/entImportFlags";
import { requiredMaxScore, savableProblem } from "@/utils/entQuestionValidity";
import { EXAM_LANGUAGES, LANGUAGE_LABEL, otherLanguage } from "@/utils/examLanguage";

const props = defineProps<{
  subjects: EntSubject[];
  initialSubjectId?: number | null;
}>();

const emit = defineEmits<{ close: []; saved: [] }>();

const modalPanelRef = ref<HTMLElement | null>(null);
// Matches the existing guard on the visible "Отмена" button (disabled
// while phase === 'saving') -- Esc shouldn't open a second way to
// interrupt an in-flight save that the button already blocks.
useModalFocusTrap(modalPanelRef, () => {
  if (phase.value === "saving") return;
  emit("close");
});

const QTYPE_LABEL: Record<EntQuestionType, string> = {
  single: "Один правильный ответ",
  multiple: "Несколько правильных ответов",
  matching: "Сопоставление",
  short_answer: "Краткий ответ",
};

type Phase = "upload" | "processing" | "preview" | "saving" | "done" | "error";

const phase = ref<Phase>("upload");
const errorMessage = ref("");
const warnings = ref<string[]>([]);
const isDragging = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);

const selectedSubjectId = ref<number | null>(props.initialSubjectId ?? props.subjects[0]?.id ?? null);
const pickedFile = ref<File | null>(null);

// reactive array of editable questions, each carrying its own `include`
// checkbox -- unchecked ones (e.g. total junk) are dropped before saving
// rather than sent to bulk-create just to be skipped there.
interface EditableQuestion extends EntQuestionImport {
  include: boolean;
  /**
   * Whether the answer shown on this card is a real one.
   *
   * Needed because a keyless question does not arrive with nothing ticked:
   * `/import-pdf` marks the first option correct so the item still passes
   * `/bulk-create`'s validation, and read literally that placeholder makes
   * every unanswered question look answered — "проставлено 105 из 119"
   * when the true figure is nine. So the parser's own verdict is trusted
   * until the teacher touches the card, and the controls after that.
   */
  answered: boolean;
}
const questions = reactive<EditableQuestion[]>([]);
const saveResult = ref<EntBulkCreateResult | null>(null);
const stats = ref<EntPdfImportStats | null>(null);

const includedCount = computed(() => questions.filter((q) => q.include).length);

// ── Answers ─────────────────────────────────────────────────────────────
// The papers this screen exists for carry no answer key at all, so "does
// this question have an answer yet" is the number the teacher is actually
// working against -- not "does the parser trust itself".

/** Whether the card's controls currently hold an answer of any kind. */
function answerIsFilled(q: EditableQuestion): boolean {
  if (q.qtype === "single" || q.qtype === "multiple") return q.choices.some((c) => c.is_correct);
  if (q.qtype === "matching") return q.match_pairs.filter((p) => p.answer_text).length >= 2;
  return q.answer_variants.some((v) => v.trim());
}

/** The question a teacher can stop worrying about: an answer that is
 * actually meant, rather than the placeholder the API had to send. */
function hasAnswer(q: EditableQuestion): boolean {
  return q.answered && answerIsFilled(q);
}

/** Ready means two things, and both have to hold: nothing the parser
 * flagged as blocking, and nothing that would make /bulk-create refuse it.
 * The second is what keeps "Сохранить готовые (N)" from being a promise of
 * N saves and a list of skips. */
function isReadyToSave(q: EditableQuestion): boolean {
  return isReady(q.flags) && savableProblem(q) === null;
}

const answeredCount = computed(() => questions.filter(hasAnswer).length);
const readyCount = computed(() => questions.filter((q) => q.include && isReadyToSave(q)).length);
const blockedCount = computed(() => questions.filter((q) => q.include && !isReadyToSave(q)).length);

/** Called after any edit to an answer. From here on the controls are the
 * truth, so the placeholder no longer counts for anything -- and dropping
 * `missing_key` is what makes the progress counter and the "save the ready
 * ones" button mean something: the flag described the *file*, and the
 * teacher has just superseded it. */
function refreshAnswerFlags(q: EditableQuestion) {
  q.answered = answerIsFilled(q);
  const had = q.flags.includes("missing_key");
  if (q.answered && had) q.flags = q.flags.filter((f) => f !== "missing_key");
  if (!q.answered && !had && q.key_source === "none") q.flags = [...q.flags, "missing_key"];
  q.needs_review = !isReadyToSave(q) || q.detected_qtype === "unknown" || !!q.parse_error;
}

/** The backend ties max_score to the question type, so changing the type on
 * the card has to carry the score with it or the save is refused. */
function onQtypeChange(q: EditableQuestion) {
  q.max_score = requiredMaxScore(q.qtype);
  refreshAnswerFlags(q);
}

// ── Language ────────────────────────────────────────────────────────────
// "Все" on open: the detector splits a bilingual file by itself, so hiding
// half of it before the teacher has looked would only make them wonder
// where the rest went.
const languageFilter = ref<ExamLanguage | "all">("all");

// Computed off `questions`, so flipping a flag on one card moves the count
// on the tabs in the same tick -- a filter that says "Қазақша (7)" while the
// list holds eight is worse than no count at all.
const languageCounts = computed<Record<ExamLanguage, number>>(() => ({
  ru: questions.filter((q) => q.language === "ru").length,
  kk: questions.filter((q) => q.language === "kk").length,
}));

// ── Review filter ───────────────────────────────────────────────────────
// Two thousand cards is not a list a teacher reads; it is one they need to
// cut down to the part that still needs them.
type ReviewFilter = "all" | "unanswered" | "flagged" | string;
const reviewFilter = ref<ReviewFilter>("all");

const unansweredCount = computed(() => questions.length - answeredCount.value);
const flaggedCount = computed(() => questions.filter((q) => q.flags.length > 0).length);
const presentFlags = computed(() => rankFlags(questions.flatMap((q) => q.flags)));
const flagCounts = computed(() => {
  const counts: Record<string, number> = {};
  for (const q of questions) for (const flag of q.flags) counts[flag] = (counts[flag] ?? 0) + 1;
  return counts;
});

function matchesFilters(q: EditableQuestion): boolean {
  if (languageFilter.value !== "all" && q.language !== languageFilter.value) return false;
  if (reviewFilter.value === "all") return true;
  if (reviewFilter.value === "unanswered") return !hasAnswer(q);
  if (reviewFilter.value === "flagged") return q.flags.length > 0;
  return q.flags.includes(reviewFilter.value);
}

const visibleQuestions = computed(() =>
  questions.map((question, index) => ({ question, index })).filter(({ question }) => matchesFilters(question)),
);

// ── Variants ────────────────────────────────────────────────────────────
// Keyed on label as well as number: a bilingual paper has a "Вариант №1"
// and a "1 нұсқа", both numbered 1, and a key pasted into one must not
// land in the other.
interface VariantGroup {
  key: string;
  label: string | null;
  entries: { question: EditableQuestion; index: number }[];
}

function variantKey(q: EntQuestionImport): string {
  return `${q.variant_id}|${q.variant_label ?? ""}`;
}

const visibleGroups = computed<VariantGroup[]>(() => {
  const groups: VariantGroup[] = [];
  for (const entry of visibleQuestions.value) {
    const key = variantKey(entry.question);
    const last = groups[groups.length - 1];
    if (last && last.key === key) last.entries.push(entry);
    else groups.push({ key, label: entry.question.variant_label, entries: [entry] });
  }
  return groups;
});

/** Every question of a variant, filters ignored: a key covers the whole
 * variant even when the teacher is looking at part of it. */
function variantQuestions(key: string): EditableQuestion[] {
  return questions.filter((q) => variantKey(q) === key);
}

function variantNumbers(key: string): number[] {
  return variantQuestions(key)
    .map((q) => q.question_number)
    .filter((n): n is number => n !== null);
}

function variantAnswered(key: string): number {
  return variantQuestions(key).filter(hasAnswer).length;
}

// ── Bulk answer key ─────────────────────────────────────────────────────
const keyInput = reactive<Record<string, string>>({});
// One snapshot per variant, taken as the key is applied, so "Отменить"
// restores exactly what was there -- including answers the teacher had
// already typed by hand.
type Snapshot = {
  index: number;
  correct: boolean[];
  pairs: { prompt_text: string; answer_text: string }[];
  flags: string[];
  // Restored along with the rest: without it "Отменить" puts the ticks
  // back but leaves the card counted as answered, so the progress figure
  // never returns to what it was.
  answered: boolean;
};
const keyUndo = reactive<Record<string, Snapshot[]>>({});
const keyResult = reactive<Record<string, string>>({});

function keyPlan(key: string) {
  const input = keyInput[key] ?? "";
  if (!input.trim()) return null;
  return planAnswerKey(input, variantNumbers(key));
}

function keyPreview(key: string): string {
  const plan = keyPlan(key);
  if (!plan) return "";
  return describePlan(plan, variantNumbers(key).length);
}

function applyAssignment(q: EditableQuestion, assignment: KeyAssignment) {
  if (q.qtype === "matching") {
    // "39: 1-A, 2-B" names prompts by their position in the left column;
    // a bare "39-AB" is read the same way, in order.
    const pairs = assignment.pairs?.length
      ? assignment.pairs.map((p) => ({ left: Number(p.left) - 1, right: p.right }))
      : assignment.letters.map((right, left) => ({ left, right }));
    for (const { left, right } of pairs) {
      const prompt = q.match_left_items[left];
      const choice = q.match_options.find((c) => c.label === right);
      if (prompt === undefined || !choice) continue;
      const existing = q.match_pairs.find((p) => p.prompt_text === prompt);
      if (existing) existing.answer_text = choice.text;
      else q.match_pairs.push({ prompt_text: prompt, answer_text: choice.text });
    }
  } else if (q.qtype === "single" || q.qtype === "multiple") {
    for (const choice of q.choices) choice.is_correct = assignment.letters.includes(choice.label);
  } else {
    q.answer_variants = [...assignment.letters];
  }
  refreshAnswerFlags(q);
}

function applyKey(key: string) {
  const plan = keyPlan(key);
  if (!plan) return;

  const byNumber = new Map(plan.matched.map((a) => [a.questionNumber, a]));
  const snapshot: Snapshot[] = [];
  let applied = 0;

  questions.forEach((q, index) => {
    if (variantKey(q) !== key || q.question_number === null) return;
    const assignment = byNumber.get(q.question_number);
    if (!assignment) return;
    snapshot.push({
      index,
      correct: q.choices.map((c) => c.is_correct),
      pairs: q.match_pairs.map((p) => ({ ...p })),
      flags: [...q.flags],
      answered: q.answered,
    });
    applyAssignment(q, assignment);
    applied += 1;
  });

  keyUndo[key] = snapshot;
  keyResult[key] = `Проставлено ответов: ${applied}. ${
    plan.missingNumbers.length ? `Без ответа: ${plan.missingNumbers.join(", ")}.` : ""
  }`;
}

function undoKey(key: string) {
  for (const entry of keyUndo[key] ?? []) {
    const q = questions[entry.index];
    if (!q) continue;
    entry.correct.forEach((value, i) => {
      const choice = q.choices[i];
      if (choice) choice.is_correct = value;
    });
    q.match_pairs.splice(0, q.match_pairs.length, ...entry.pairs);
    q.flags = [...entry.flags];
    q.answered = entry.answered;
    q.needs_review = !isReadyToSave(q) || q.detected_qtype === "unknown" || !!q.parse_error;
  }
  delete keyUndo[key];
  keyResult[key] = "Ответы варианта возвращены к исходным.";
}

// ── Keyboard review ─────────────────────────────────────────────────────
// A/B/C/D picks an answer, Enter moves on. Forty questions become forty
// seconds, which is the difference between the import being used and not.
const cardRefs = new Map<number, HTMLElement>();

function registerCard(index: number, el: unknown) {
  if (el instanceof HTMLElement) cardRefs.set(index, el);
  else cardRefs.delete(index);
}

function focusCard(index: number) {
  nextTick(() => cardRefs.get(index)?.focus());
}

function focusNextFrom(index: number) {
  const order = visibleQuestions.value.map((entry) => entry.index);
  const position = order.indexOf(index);
  const next = order[position + 1];
  if (next !== undefined) focusCard(next);
}

function onCardKey(event: KeyboardEvent, q: EditableQuestion, index: number) {
  // Never steal a key from a field the teacher is typing in.
  const target = event.target as HTMLElement | null;
  if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;

  if (event.key === "Enter" || event.key === "Escape") {
    event.preventDefault();
    focusNextFrom(index);
    return;
  }
  const letter = event.key.toUpperCase();
  if (!/^[A-H]$/.test(letter)) return;
  const choice = q.choices.find((c) => c.label === letter);
  if (!choice) return;

  event.preventDefault();
  if (q.qtype === "multiple") choice.is_correct = !choice.is_correct;
  else for (const c of q.choices) c.is_correct = c === choice;
  refreshAnswerFlags(q);
}

function toggleLanguage(q: EditableQuestion) {
  q.language = otherLanguage(q.language);
}

function onFilePicked(file: File | null) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".pdf")) {
    errorMessage.value = "Выберите файл в формате PDF";
    return;
  }
  errorMessage.value = "";
  pickedFile.value = file;
}

function onDrop(event: DragEvent) {
  isDragging.value = false;
  const file = event.dataTransfer?.files?.[0] ?? null;
  onFilePicked(file);
}

function onFileInputChange(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0] ?? null;
  onFilePicked(file);
}

async function handleUpload() {
  if (!pickedFile.value || !selectedSubjectId.value) return;
  phase.value = "processing";
  errorMessage.value = "";
  try {
    const result = await importEntQuestionsFromPdf(selectedSubjectId.value, pickedFile.value);
    warnings.value = result.warnings;
    stats.value = result.stats;
    questions.splice(
      0,
      questions.length,
      // `missing_key` is the parser saying the file carried no answer for
      // this question, whatever the placeholder tick on option A suggests.
      ...result.questions.map((q) => ({ ...q, include: true, answered: !q.flags.includes("missing_key") })),
    );
    phase.value = "preview";
  } catch {
    errorMessage.value = "Не удалось обработать PDF-файл. Попробуйте другой файл.";
    phase.value = "error";
  }
}

function addChoice(q: EditableQuestion) {
  // No label: a choice the teacher typed was never on a page, so there is
  // no printed letter to show next to it.
  q.choices.push({ text: "", is_correct: false, label: "", raw_label: "" });
}

function addMatchPair(q: EditableQuestion) {
  q.match_pairs.push({ prompt_text: "", answer_text: "" });
}

function addAnswerVariant(q: EditableQuestion) {
  q.answer_variants.push("");
}

function removeQuestion(index: number) {
  questions.splice(index, 1);
}

/** The option currently paired with a recovered prompt, as a label. */
function pairedLabel(q: EditableQuestion, prompt: string): string {
  const pair = q.match_pairs.find((p) => p.prompt_text === prompt);
  if (!pair) return "";
  return q.match_options.find((c) => c.text === pair.answer_text)?.label ?? "";
}

function setPairedLabel(q: EditableQuestion, prompt: string, label: string) {
  const choice = q.match_options.find((c) => c.label === label);
  const existing = q.match_pairs.find((p) => p.prompt_text === prompt);
  if (!choice) {
    if (existing) q.match_pairs.splice(q.match_pairs.indexOf(existing), 1);
  } else if (existing) {
    existing.answer_text = choice.text;
  } else {
    q.match_pairs.push({ prompt_text: prompt, answer_text: choice.text });
  }
  refreshAnswerFlags(q);
}

/**
 * The question as `/bulk-create` will accept it.
 *
 * `EntQuestionIn` rejects any answer field its type does not use, so the
 * card's working state cannot be posted as-is: a matching question carries
 * `choices` (the right-hand column it is paired against — see the adapter),
 * and a question whose type the teacher changed still carries whatever the
 * previous type filled in. Both would 422 the entire batch, so exactly one
 * answer field is sent and the rest are dropped.
 */
function forSaving(q: EditableQuestion): EntQuestionImport {
  const base = { ...q, choices: [], match_pairs: [], answer_variants: [] };
  if (q.qtype === "single" || q.qtype === "multiple") return { ...base, choices: q.choices };
  if (q.qtype === "matching") {
    return { ...base, match_pairs: q.match_pairs.filter((p) => p.prompt_text && p.answer_text) };
  }
  return { ...base, answer_variants: q.answer_variants.filter((v) => v.trim()) };
}

async function save(only: "all" | "ready") {
  if (!selectedSubjectId.value) return;
  const toSave = questions.filter((q) => q.include && (only === "all" || isReadyToSave(q))).map(forSaving);
  if (!toSave.length) return;

  phase.value = "saving";
  try {
    saveResult.value = await bulkCreateEntQuestions(selectedSubjectId.value, toSave);
    phase.value = "done";
    emit("saved");
  } catch {
    errorMessage.value = "Не удалось сохранить вопросы. Попробуйте ещё раз.";
    phase.value = "preview";
  }
}

function confidencePct(c: number): string {
  return `${Math.round(c * 100)}%`;
}

function sourceLines(q: EditableQuestion): string {
  const [first, last] = q.raw_line_range;
  if (first === undefined) return "";
  return first === last ? `строка ${first + 1}` : `строки ${first + 1}–${last + 1}`;
}

function choiceLabel(c: { label: string; raw_label: string }): string {
  // The printed glyph is what the teacher will look for on their page;
  // the canonical label only matters when the two differ.
  if (!c.raw_label) return c.label;
  return c.raw_label.toUpperCase() === c.label ? c.label : `${c.raw_label} → ${c.label}`;
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" @click.self="emit('close')">
    <div
      ref="modalPanelRef"
      role="dialog"
      aria-modal="true"
      class="card flex max-h-[92dvh] w-full max-w-4xl flex-col overflow-hidden"
    >
      <div class="flex items-center justify-between px-5 pb-4 pt-5">
        <h2 class="text-lg font-semibold text-ink">Импорт вопросов из PDF</h2>
        <button
          class="flex h-11 w-11 items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-paper-2 hover:text-ink"
          aria-label="Закрыть"
          @click="emit('close')"
        >
          <X :size="18" :stroke-width="1.8" />
        </button>
      </div>

      <!-- ── Step 1: upload ─────────────────────────────────────────── -->
      <template v-if="phase === 'upload' || phase === 'error'">
        <div class="px-5 pb-5">
          <label class="mb-4 block text-sm">
            <span class="mb-1.5 block font-medium text-ink">Предмет</span>
            <select v-model.number="selectedSubjectId" class="input">
              <option v-for="s in subjects" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </label>

          <div
            class="flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed p-10 text-center transition-colors duration-150"
            :class="isDragging ? 'border-moss bg-moss/5' : 'border-line-strong'"
            @dragover.prevent="isDragging = true"
            @dragleave.prevent="isDragging = false"
            @drop.prevent="onDrop"
            @click="fileInput?.click()"
          >
            <FileText :size="30" :stroke-width="1.5" class="text-ink-3" />
            <p class="text-sm font-medium text-ink">
              {{ pickedFile ? pickedFile.name : "Перетащите PDF сюда или нажмите, чтобы выбрать файл" }}
            </p>
            <p class="text-xs text-ink-3">Только .pdf</p>
            <input ref="fileInput" type="file" accept="application/pdf" class="hidden" @change="onFileInputChange" />
          </div>

          <p v-if="errorMessage" class="mt-3 text-sm text-clay">{{ errorMessage }}</p>

          <div class="mt-5 flex justify-end gap-2">
            <BaseButton variant="secondary" @click="emit('close')">Отмена</BaseButton>
            <BaseButton :disabled="!pickedFile || !selectedSubjectId" @click="handleUpload">Обработать</BaseButton>
          </div>
        </div>
      </template>

      <!-- ── Step 2: processing ─────────────────────────────────────── -->
      <div v-else-if="phase === 'processing'" class="flex flex-col items-center gap-3 px-5 pb-10 pt-2">
        <div class="h-10 w-10 animate-spin rounded-full border-4 border-line-strong border-t-moss"></div>
        <p class="text-sm text-ink-2">Извлекаем текст и распознаём вопросы…</p>
      </div>

      <!-- ── Step 3: preview ────────────────────────────────────────── -->
      <template v-else-if="phase === 'preview' || phase === 'saving'">
        <!-- ── Sticky header: stats + filters stay visible while the card
             list below scrolls -- a teacher forty cards in still has the
             language/review tabs and the "N recognized" caption in view. ── -->
        <div class="sticky top-0 z-20 space-y-3 border-b border-line bg-paper px-5 pb-3">
          <div class="space-y-1">
            <p v-for="(w, i) in warnings" :key="i" class="flex items-start gap-1.5 rounded-md bg-marigold/10 px-2 py-1 text-sm text-ink">
              <TriangleAlert :size="14" :stroke-width="1.8" class="mt-0.5 shrink-0" />{{ w }}
            </p>
            <p class="text-sm text-ink-2">
              Распознано вопросов: {{ questions.length }}. Проставлено ответов:
              <strong class="text-ink">{{ answeredCount }}</strong> из {{ questions.length }}.
            </p>
            <!-- Said plainly and once: in these papers the answers are simply
                 not in the file, and a teacher who does not know that reads
                 2000 red cards as 2000 parsing failures. -->
            <p v-if="unansweredCount > questions.length / 2" class="rounded-md bg-marigold/10 px-2 py-1 text-sm text-ink">
              В этом файле нет правильных ответов — их нужно проставить. Быстрее всего вставить ключ
              варианта в поле под его заголовком.
            </p>
            <p v-if="stats" class="text-xs text-ink-3">
              Обработано строк: {{ stats.total_lines }} · найдено блоков: {{ stats.total_blocks_detected }}
              <span v-if="stats.variants_detected > 1"> · вариантов: {{ stats.variants_detected }}</span>
              <span v-if="stats.duplicate_variant_headers">
                · повторных заголовков объединено: {{ stats.duplicate_variant_headers }}</span
              >
            </p>
          </div>

          <!-- ── Filters ──────────────────────────────────────────────
               A view over the list, not a selection: the checkboxes decide
               what gets saved, so a hidden card that is still ticked is still
               saved (and the note below says so). -->
          <div v-if="questions.length" class="space-y-2">
            <div class="flex flex-wrap items-center gap-2">
              <button
                type="button"
                class="rounded-xl px-3 py-1.5 text-xs font-medium transition-colors duration-150"
                :class="languageFilter === 'all' ? 'bg-moss text-moss-fg' : 'bg-paper-2 text-ink-2 hover:bg-line hover:text-ink'"
                @click="languageFilter = 'all'"
              >
                Все языки ({{ questions.length }})
              </button>
              <button
                v-for="language in EXAM_LANGUAGES"
                :key="language"
                type="button"
                class="rounded-xl px-3 py-1.5 text-xs font-medium transition-colors duration-150"
                :class="languageFilter === language ? 'bg-moss text-moss-fg' : 'bg-paper-2 text-ink-2 hover:bg-line hover:text-ink'"
                @click="languageFilter = language"
              >
                {{ LANGUAGE_LABEL[language] }} ({{ languageCounts[language] }})
              </button>
            </div>

            <div class="flex flex-wrap items-center gap-2">
              <button
                type="button"
                class="rounded-lg border px-2.5 py-1 text-xs transition-colors duration-150"
                :class="reviewFilter === 'all' ? 'border-line-strong bg-paper-2 font-medium text-ink' : 'border-line text-ink-2 hover:bg-paper-2'"
                @click="reviewFilter = 'all'"
              >
                Все вопросы
              </button>
              <button
                type="button"
                class="rounded-lg border px-2.5 py-1 text-xs transition-colors duration-150"
                :class="
                  reviewFilter === 'unanswered' ? 'border-line-strong bg-paper-2 font-medium text-ink' : 'border-line text-ink-2 hover:bg-paper-2'
                "
                @click="reviewFilter = 'unanswered'"
              >
                Без ответа ({{ unansweredCount }})
              </button>
              <button
                type="button"
                class="rounded-lg border px-2.5 py-1 text-xs transition-colors duration-150"
                :class="
                  reviewFilter === 'flagged' ? 'border-line-strong bg-paper-2 font-medium text-ink' : 'border-line text-ink-2 hover:bg-paper-2'
                "
                @click="reviewFilter = 'flagged'"
              >
                С замечаниями ({{ flaggedCount }})
              </button>
              <select
                :value="presentFlags.includes(reviewFilter) ? reviewFilter : ''"
                class="rounded-lg border border-line bg-paper px-2 py-1 text-xs text-ink"
                @change="reviewFilter = ($event.target as HTMLSelectElement).value || 'all'"
              >
                <option value="">По типу замечания…</option>
                <option v-for="flag in presentFlags" :key="flag" :value="flag">
                  {{ flagInfo(flag).label }} ({{ flagCounts[flag] }})
                </option>
              </select>
              <span class="text-xs text-ink-3">
                Фильтры только скрывают карточки — сохранятся все отмеченные ({{ includedCount }}).
              </span>
            </div>
          </div>
        </div>

        <!-- ── Scrollable card list: vertical scroll only, contained so no
             card can push the modal wider than the viewport. ── -->
        <div class="w-full max-w-full flex-1 space-y-3 overflow-x-hidden overflow-y-auto px-5 py-3 max-h-[65vh]">
          <template v-for="group in visibleGroups" :key="group.key">
            <!-- ── Variant header, with the bulk key field ─────────────
                 The single most important control on this screen: without
                 it a 2000-question file is 2000 clicks. -->
            <div class="sticky top-0 z-10 -mx-1 space-y-2 border-b border-line bg-paper px-1 pb-2 pt-2">
              <p v-if="group.label" class="text-xs font-semibold uppercase tracking-wide text-ink-2">
                {{ group.label }}
                <span class="ml-1 font-normal normal-case tracking-normal text-ink-3">
                  — с ответами {{ variantAnswered(group.key) }} из {{ variantQuestions(group.key).length }}
                </span>
              </p>
              <div class="flex flex-wrap items-start gap-2">
                <input
                  v-model="keyInput[group.key]"
                  type="text"
                  placeholder="Вставить ключи варианта: 1-B, 2-C, 3-A …"
                  class="min-w-[16rem] flex-1 rounded-lg border border-line-strong bg-paper px-2.5 py-1.5 text-xs text-ink"
                  @keydown.enter.prevent="applyKey(group.key)"
                />
                <BaseButton
                  class="!px-3 !py-1.5 !text-xs"
                  :disabled="!keyPlan(group.key)?.matched.length"
                  @click="applyKey(group.key)"
                >
                  Применить
                </BaseButton>
                <BaseButton
                  v-if="keyUndo[group.key]"
                  variant="secondary"
                  class="!px-3 !py-1.5 !text-xs"
                  @click="undoKey(group.key)"
                >
                  Отменить
                </BaseButton>
              </div>
              <!-- Shown before anything is applied: a bulk edit the teacher
                   cannot see the shape of first is one they cannot trust. -->
              <p v-if="keyPreview(group.key)" class="text-xs text-ink-3">{{ keyPreview(group.key) }}</p>
              <p v-if="keyResult[group.key]" class="text-xs text-moss">
                {{ keyResult[group.key] }}
              </p>
            </div>

            <!-- ── Card states, ranked by how urgent they are:
                 · blocking (would fail /bulk-create) is a real validation
                   error -- clay, the same tone as any other failed-save state.
                 · needs_review (advisory: missing key, unknown type, parse
                   error) is exactly the "human needs to look at this" case
                   `.marker-edge` exists for -- one flagged question in a
                   list of hundreds, not decoration.
                 · otherwise plain. -->
            <div
              v-for="{ question: q, index: i } in group.entries"
              :key="i"
              :ref="(el) => registerCard(i, el)"
              tabindex="0"
              class="w-full min-w-0 max-w-full space-y-3 overflow-x-hidden rounded-xl border p-3 text-sm outline-none focus:ring-2 focus:ring-moss/60"
              :class="
                !isReadyToSave(q)
                  ? 'border-clay/40 bg-clay/5'
                  : q.needs_review
                    ? 'marker-edge bg-marigold/5'
                    : 'border-line'
              "
              @keydown="onCardKey($event, q, i)"
            >
              <div class="flex flex-wrap items-center gap-2">
                <input v-model="q.include" type="checkbox" class="h-4 w-4 accent-moss" />
                <span v-if="q.question_number !== null" class="text-xs font-semibold text-ink-3">
                  №{{ q.question_number }}
                </span>
                <BaseBadge :tone="hasAnswer(q) ? 'success' : 'warning'">
                  {{ hasAnswer(q) ? "Ответ проставлен" : "Без ответа" }} · {{ confidencePct(q.confidence) }}
                </BaseBadge>
                <!-- One click flips the language: with two of them a dropdown
                     costs the same click and reads worse. -->
                <button
                  type="button"
                  class="rounded-lg border border-line-strong px-2 py-1 text-xs text-ink-2 transition-colors duration-150 hover:border-line-strong hover:bg-paper-2"
                  :title="`Язык вопроса — нажмите, чтобы переключить на «${LANGUAGE_LABEL[otherLanguage(q.language)]}»`"
                  @click="toggleLanguage(q)"
                >
                  {{ LANGUAGE_LABEL[q.language] }}
                </button>
                <select v-model="q.qtype" class="rounded-lg border border-line bg-paper px-2 py-1 text-xs text-ink" @change="onQtypeChange(q)">
                  <option v-for="(label, value) in QTYPE_LABEL" :key="value" :value="value">{{ label }}</option>
                </select>
                <span v-if="sourceLines(q)" class="text-xs text-ink-3">{{ sourceLines(q) }}</span>
                <button class="ml-auto text-xs text-clay hover:underline" @click="removeQuestion(i)">
                  Удалить
                </button>
              </div>

              <!-- Named faults instead of one amber wash: what to look at,
                   and whether it blocks saving. -->
              <div v-if="q.flags.length" class="flex flex-wrap gap-1.5">
                <span
                  v-for="flag in rankFlags(q.flags)"
                  :key="flag"
                  class="rounded-md border px-1.5 py-0.5 text-[11px]"
                  :class="FLAG_CHIP_CLASS[flagInfo(flag).tone]"
                >
                  <component :is="flagInfo(flag).tone === 'danger' ? TriangleAlert : Info" :size="12" :stroke-width="1.8" class="mr-0.5 inline align-[-2px]" />{{ flagInfo(flag).label }}
                </span>
              </div>

              <!-- Named at the moment it can be fixed, not after the save
                   has already skipped it. -->
              <p v-if="savableProblem(q)" class="text-xs text-clay">
                Не сохранится: {{ savableProblem(q) }}
              </p>

              <p v-if="q.parse_error" class="text-xs text-clay">
                Не удалось разобрать этот блок ({{ q.parse_error }}) — текст ниже приведён как есть из файла.
              </p>
              <p v-else-if="q.detected_qtype === 'unknown'" class="text-xs text-ink">
                Тип вопроса определить не удалось — выберите его и заполните ответы вручную.
              </p>
              <p v-else-if="q.key_source === 'highlight'" class="text-xs text-ink">
                Ответ взят из выделения цветом в PDF (в файле нет текстового «Ответ:») — проверьте его.
              </p>

              <textarea
                v-model="q.text"
                rows="2"
                class="w-full max-w-full break-words rounded-lg border border-line-strong bg-paper px-3 py-2 text-sm text-ink"
                placeholder="Текст вопроса"
              />

              <template v-if="q.qtype === 'single' || q.qtype === 'multiple'">
                <div v-for="(c, ci) in q.choices" :key="ci" class="flex items-center gap-2">
                  <input
                    v-model="c.is_correct"
                    type="checkbox"
                    class="h-4 w-4 accent-moss"
                    @change="refreshAnswerFlags(q)"
                  />
                  <span v-if="choiceLabel(c)" class="w-14 shrink-0 text-xs text-ink-3">{{ choiceLabel(c) }}</span>
                  <input v-model="c.text" class="input min-w-0 flex-1 whitespace-normal break-words px-2 py-1.5" />
                </div>
                <button class="text-xs text-moss hover:underline" @click="addChoice(q)">+ вариант</button>
              </template>

              <template v-else-if="q.qtype === 'matching'">
                <!-- With the prompts recovered from the PDF's table, pairing
                     is a letter per prompt rather than two free-text columns
                     the teacher has to retype. -->
                <template v-if="q.match_left_items.length && q.match_options.length">
                  <div v-for="(prompt, pi) in q.match_left_items" :key="pi" class="flex items-center gap-2">
                    <span class="w-6 shrink-0 text-xs text-ink-3">{{ pi + 1 }}.</span>
                    <span class="min-w-0 flex-1 whitespace-normal break-words text-sm text-ink">{{ prompt }}</span>
                    <select
                      class="shrink-0 rounded-lg border border-line bg-paper px-2 py-1 text-xs text-ink"
                      :value="pairedLabel(q, prompt)"
                      @change="setPairedLabel(q, prompt, ($event.target as HTMLSelectElement).value)"
                    >
                      <option value="">—</option>
                      <option v-for="c in q.match_options" :key="c.label" :value="c.label">
                        {{ c.label }}) {{ c.text }}
                      </option>
                    </select>
                  </div>
                </template>
                <!-- No prompts recovered (a file whose tables were not
                     ruled): fall back to two free-text columns. -->
                <template v-else>
                  <div v-for="(p, pi) in q.match_pairs" :key="pi" class="flex items-center gap-2">
                    <input v-model="p.prompt_text" placeholder="Слева" class="input min-w-0 flex-1 whitespace-normal break-words px-2 py-1.5" />
                    <input v-model="p.answer_text" placeholder="Справа" class="input min-w-0 flex-1 whitespace-normal break-words px-2 py-1.5" />
                  </div>
                </template>
                <button
                  v-if="!q.match_left_items.length"
                  class="text-xs text-moss hover:underline"
                  @click="addMatchPair(q)"
                >
                  + пара
                </button>
              </template>

              <template v-else>
                <div v-for="(_, vi) in q.answer_variants" :key="vi" class="flex items-center gap-2">
                  <input
                    v-model="q.answer_variants[vi]"
                    placeholder="Принимаемый ответ"
                    class="input min-w-0 flex-1 whitespace-normal break-words px-2 py-1.5"
                  />
                </div>
                <button class="text-xs text-moss hover:underline" @click="addAnswerVariant(q)">+ вариант написания</button>
              </template>
            </div>
          </template>

          <p v-if="!questions.length" class="text-sm text-ink-2">Ничего не распознано.</p>
          <p v-else-if="!visibleQuestions.length" class="text-sm text-ink-2">
            Под выбранные фильтры не подходит ни один вопрос.
          </p>
        </div>

        <p v-if="errorMessage" class="px-5 text-sm text-clay">{{ errorMessage }}</p>

        <!-- ── Sticky footer: save actions stay reachable without scrolling
             to the bottom of a long card list. ── -->
        <div class="sticky bottom-0 z-20 flex flex-wrap items-center justify-end gap-2 border-t border-line bg-paper p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
          <p class="mr-auto text-xs text-ink-3">
            Подсказка: выберите карточку и нажимайте A/B/C/D — ответ, Enter — следующий вопрос.
          </p>
          <BaseButton variant="secondary" :disabled="phase === 'saving'" @click="emit('close')">Отмена</BaseButton>
          <!-- Saving in parts, so a teacher who did thirty variants today
               keeps them instead of losing the lot to the ten they have not
               reached yet. When anything is blocked, *this* is the primary
               action: a question with no answer is saved with a placeholder
               one, and "сохранить всё" must say so rather than look like
               the safe default. -->
          <template v-if="blockedCount">
            <BaseButton
              variant="secondary"
              :disabled="!includedCount || phase === 'saving'"
              :title="`${blockedCount} вопрос(ов) без ответа будут сохранены с первым вариантом, отмеченным верным`"
              @click="save('all')"
            >
              Сохранить все, включая {{ blockedCount }} без ответа
            </BaseButton>
            <BaseButton :disabled="!readyCount || phase === 'saving'" @click="save('ready')">
              {{ phase === "saving" ? "Сохраняем…" : `Сохранить готовые (${readyCount})` }}
            </BaseButton>
          </template>
          <BaseButton v-else :disabled="!includedCount || phase === 'saving'" @click="save('all')">
            {{ phase === "saving" ? "Сохраняем…" : `Сохранить ${includedCount} вопросов в базу` }}
          </BaseButton>
        </div>
      </template>

      <!-- ── Step 4: done ───────────────────────────────────────────── -->
      <div v-else-if="phase === 'done' && saveResult" class="flex flex-col items-center gap-3 px-5 pb-10 pt-2 text-center">
        <CircleCheck :size="30" :stroke-width="1.5" class="text-green-700 dark:text-green-500" />
        <p class="font-medium text-ink">Сохранено вопросов: {{ saveResult.created_count }}</p>
        <div v-if="saveResult.skipped.length" class="max-w-sm text-sm text-ink-2">
          <p class="mb-1 rounded-md bg-marigold/10 px-2 py-1 text-ink">Пропущено: {{ saveResult.skipped.length }}</p>
          <ul class="space-y-1 text-left">
            <li v-for="s in saveResult.skipped" :key="s.index">№{{ s.index + 1 }}: {{ s.error }}</li>
          </ul>
        </div>
        <BaseButton @click="emit('close')">Готово</BaseButton>
      </div>
    </div>
  </div>
</template>
