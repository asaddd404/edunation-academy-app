<script setup lang="ts">
import { computed, reactive, ref } from "vue";

import { bulkCreateEntQuestions, importEntQuestionsFromPdf } from "@/api/ent";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type {
  EntBulkCreateResult,
  EntPdfImportStats,
  EntQuestionImport,
  EntQuestionType,
  EntSubject,
  ExamLanguage,
} from "@/types";
import { EXAM_LANGUAGES, LANGUAGE_FLAG, LANGUAGE_LABEL, otherLanguage } from "@/utils/examLanguage";

const props = defineProps<{
  subjects: EntSubject[];
  initialSubjectId?: number | null;
}>();

const emit = defineEmits<{ close: []; saved: [] }>();

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
}
const questions = reactive<EditableQuestion[]>([]);
const saveResult = ref<EntBulkCreateResult | null>(null);
const stats = ref<EntPdfImportStats | null>(null);

const includedCount = computed(() => questions.filter((q) => q.include).length);
const reviewCount = computed(() => questions.filter((q) => q.needs_review).length);

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

const visibleQuestions = computed(() =>
  questions
    .map((question, index) => ({ question, index }))
    .filter(({ question }) => languageFilter.value === "all" || question.language === languageFilter.value),
);

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
    questions.splice(0, questions.length, ...result.questions.map((q) => ({ ...q, include: true })));
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

async function handleSave() {
  if (!selectedSubjectId.value) return;
  const toSave = questions.filter((q) => q.include);
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

// A file of fifty variants arrives as one flat list. Rather than nesting
// the reactive array (which every edit handler would then have to walk),
// the list stays flat and a heading is drawn wherever the variant changes.
// Measured against the previous *visible* card, so filtering to one
// language doesn't leave headings for variants that are no longer shown.
function startsVariant(position: number): boolean {
  const entry = visibleQuestions.value[position];
  if (!entry?.question.variant_label) return false;
  const previous = visibleQuestions.value[position - 1];
  return !previous || previous.question.variant_id !== entry.question.variant_id;
}

function choiceLabel(c: { label: string; raw_label: string }): string {
  // The printed glyph is what the teacher will look for on their page;
  // the canonical label only matters when the two differ.
  if (!c.raw_label) return c.label;
  return c.raw_label.toUpperCase() === c.label ? c.label : `${c.raw_label} → ${c.label}`;
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" @click.self="emit('close')">
    <div class="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-2xl border border-border bg-card p-5">
      <div class="mb-4 flex items-center justify-between">
        <h2 class="text-lg font-semibold">Импорт вопросов из PDF</h2>
        <button class="text-fg/50 hover:text-fg" @click="emit('close')">✕</button>
      </div>

      <!-- ── Step 1: upload ─────────────────────────────────────────── -->
      <template v-if="phase === 'upload' || phase === 'error'">
        <label class="mb-4 block text-sm">
          <span class="mb-1.5 block font-medium text-fg/80">Предмет</span>
          <select
            v-model.number="selectedSubjectId"
            class="w-full rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm"
          >
            <option v-for="s in subjects" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </label>

        <div
          class="flex flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed p-10 text-center transition-colors duration-150"
          :class="isDragging ? 'border-indigo-500 bg-indigo-500/5' : 'border-fg/20'"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="onDrop"
          @click="fileInput?.click()"
        >
          <span class="text-3xl">📄</span>
          <p class="text-sm font-medium">
            {{ pickedFile ? pickedFile.name : "Перетащите PDF сюда или нажмите, чтобы выбрать файл" }}
          </p>
          <p class="text-xs text-fg/50">Только .pdf</p>
          <input ref="fileInput" type="file" accept="application/pdf" class="hidden" @change="onFileInputChange" />
        </div>

        <p v-if="errorMessage" class="mt-3 text-sm text-red-600 dark:text-red-500">{{ errorMessage }}</p>

        <div class="mt-5 flex justify-end gap-2">
          <BaseButton variant="secondary" @click="emit('close')">Отмена</BaseButton>
          <BaseButton :disabled="!pickedFile || !selectedSubjectId" @click="handleUpload">Обработать</BaseButton>
        </div>
      </template>

      <!-- ── Step 2: processing ─────────────────────────────────────── -->
      <div v-else-if="phase === 'processing'" class="flex flex-col items-center gap-3 py-16">
        <div class="h-10 w-10 animate-spin rounded-full border-4 border-fg/20 border-t-indigo-500"></div>
        <p class="text-sm text-fg/60">Извлекаем текст и распознаём вопросы…</p>
      </div>

      <!-- ── Step 3: preview ────────────────────────────────────────── -->
      <template v-else-if="phase === 'preview' || phase === 'saving'">
        <div class="mb-3 space-y-1">
          <p v-for="(w, i) in warnings" :key="i" class="text-sm text-amber-700 dark:text-amber-400">⚠ {{ w }}</p>
          <p class="text-sm text-fg/60">
            Распознано вопросов: {{ questions.length }}<span v-if="reviewCount">, из них требуют проверки:
              {{ reviewCount }}</span
            >. Проверьте отмеченные жёлтым — парсер не уверен в типе или ответе.
          </p>
          <p v-if="stats" class="text-xs text-fg/40">
            Обработано строк: {{ stats.total_lines }} · найдено блоков: {{ stats.total_blocks_detected }}
            <span v-if="stats.variants_detected > 1"> · вариантов: {{ stats.variants_detected }}</span>
          </p>
        </div>

        <!-- ── Language quick filter ──────────────────────────────────
             A view over the list, not a selection: the checkboxes decide
             what gets saved, so a hidden card that is still ticked is still
             saved (and the note below says so). -->
        <div v-if="questions.length" class="mb-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-150"
            :class="
              languageFilter === 'all'
                ? 'bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-500/25'
                : 'bg-fg/5 text-fg/60 hover:bg-fg/10 hover:text-fg'
            "
            @click="languageFilter = 'all'"
          >
            Все ({{ questions.length }})
          </button>
          <button
            v-for="language in EXAM_LANGUAGES"
            :key="language"
            type="button"
            class="rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-150"
            :class="
              languageFilter === language
                ? 'bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-500/25'
                : 'bg-fg/5 text-fg/60 hover:bg-fg/10 hover:text-fg'
            "
            @click="languageFilter = language"
          >
            {{ LANGUAGE_FLAG[language] }} Только {{ LANGUAGE_LABEL[language] }} ({{ languageCounts[language] }})
          </button>
          <span v-if="languageFilter !== 'all'" class="text-xs text-fg/40">
            Фильтр только скрывает карточки — сохранятся все отмеченные ({{ includedCount }}).
          </span>
        </div>

        <div class="flex-1 space-y-3 overflow-y-auto pr-1">
          <template v-for="({ question: q, index: i }, position) in visibleQuestions" :key="i">
            <p
              v-if="startsVariant(position)"
              class="sticky top-0 z-10 -mx-1 bg-card px-1 pb-1 pt-2 text-xs font-semibold uppercase tracking-wide text-fg/50"
            >
              {{ q.variant_label }}
            </p>
          <div
            class="space-y-3 rounded-xl border p-3 text-sm"
            :class="q.needs_review ? 'border-amber-500/50 bg-amber-500/5' : 'border-fg/10'"
          >
            <div class="flex flex-wrap items-center gap-2">
              <input type="checkbox" v-model="q.include" class="h-4 w-4 accent-indigo-600" />
              <BaseBadge :tone="q.needs_review ? 'warning' : 'success'">
                {{ q.needs_review ? "Требует проверки" : "Уверенно" }} · {{ confidencePct(q.confidence) }}
              </BaseBadge>
              <!-- One click flips the language: with two of them a dropdown
                   costs the same click and reads worse. -->
              <button
                type="button"
                class="rounded-lg border border-fg/20 px-2 py-1 text-xs transition-colors duration-150 hover:border-fg/40 hover:bg-fg/5"
                :title="`Язык вопроса — нажмите, чтобы переключить на «${LANGUAGE_LABEL[otherLanguage(q.language)]}»`"
                @click="toggleLanguage(q)"
              >
                {{ LANGUAGE_FLAG[q.language] }} {{ LANGUAGE_LABEL[q.language] }}
              </button>
              <select v-model="q.qtype" class="rounded-lg border border-fg/20 bg-transparent px-2 py-1 text-xs">
                <option v-for="(label, value) in QTYPE_LABEL" :key="value" :value="value">{{ label }}</option>
              </select>
              <span v-if="sourceLines(q)" class="text-xs text-fg/40">{{ sourceLines(q) }}</span>
              <button class="ml-auto text-xs text-red-600 hover:underline dark:text-red-500" @click="removeQuestion(i)">
                Удалить
              </button>
            </div>

            <p v-if="q.parse_error" class="text-xs text-red-600 dark:text-red-500">
              Не удалось разобрать этот блок ({{ q.parse_error }}) — текст ниже приведён как есть из файла.
            </p>
            <p v-else-if="q.detected_qtype === 'unknown'" class="text-xs text-amber-700 dark:text-amber-400">
              Тип вопроса определить не удалось — выберите его и заполните ответы вручную.
            </p>
            <p v-else-if="q.key_source === 'highlight'" class="text-xs text-amber-700 dark:text-amber-400">
              Ответ взят из выделения цветом в PDF (в файле нет текстового «Ответ:») — проверьте его.
            </p>

            <textarea
              v-model="q.text"
              rows="2"
              class="w-full rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm"
              placeholder="Текст вопроса"
            />

            <template v-if="q.qtype === 'single' || q.qtype === 'multiple'">
              <div v-for="(c, ci) in q.choices" :key="ci" class="flex items-center gap-2">
                <input v-model="c.is_correct" type="checkbox" class="h-4 w-4 accent-indigo-600" />
                <span v-if="choiceLabel(c)" class="w-14 shrink-0 text-xs text-fg/40">{{ choiceLabel(c) }}</span>
                <input v-model="c.text" class="flex-1 rounded-lg border border-fg/20 bg-transparent px-2 py-1.5 text-sm" />
              </div>
              <button class="text-xs text-accent hover:underline" @click="addChoice(q)">+ вариант</button>
            </template>

            <template v-else-if="q.qtype === 'matching'">
              <div v-for="(p, pi) in q.match_pairs" :key="pi" class="flex items-center gap-2">
                <input
                  v-model="p.prompt_text"
                  placeholder="Слева"
                  class="flex-1 rounded-lg border border-fg/20 bg-transparent px-2 py-1.5 text-sm"
                />
                <input
                  v-model="p.answer_text"
                  placeholder="Справа"
                  class="flex-1 rounded-lg border border-fg/20 bg-transparent px-2 py-1.5 text-sm"
                />
              </div>
              <button class="text-xs text-accent hover:underline" @click="addMatchPair(q)">+ пара</button>
            </template>

            <template v-else>
              <div v-for="(_, vi) in q.answer_variants" :key="vi" class="flex items-center gap-2">
                <input
                  v-model="q.answer_variants[vi]"
                  placeholder="Принимаемый ответ"
                  class="flex-1 rounded-lg border border-fg/20 bg-transparent px-2 py-1.5 text-sm"
                />
              </div>
              <button class="text-xs text-accent hover:underline" @click="addAnswerVariant(q)">+ вариант написания</button>
            </template>
          </div>
          </template>

          <p v-if="!questions.length" class="text-sm text-fg/60">Ничего не распознано.</p>
          <p v-else-if="!visibleQuestions.length" class="text-sm text-fg/60">
            В файле нет вопросов на выбранном языке.
          </p>
        </div>

        <p v-if="errorMessage" class="mt-3 text-sm text-red-600 dark:text-red-500">{{ errorMessage }}</p>

        <div class="mt-4 flex justify-end gap-2 border-t border-border pt-4">
          <BaseButton variant="secondary" :disabled="phase === 'saving'" @click="emit('close')">Отмена</BaseButton>
          <BaseButton :disabled="!includedCount || phase === 'saving'" @click="handleSave">
            {{ phase === "saving" ? "Сохраняем…" : `Сохранить ${includedCount} вопросов в базу` }}
          </BaseButton>
        </div>
      </template>

      <!-- ── Step 4: done ───────────────────────────────────────────── -->
      <div v-else-if="phase === 'done' && saveResult" class="flex flex-col items-center gap-3 py-10 text-center">
        <span class="text-3xl">✅</span>
        <p class="font-medium">Сохранено вопросов: {{ saveResult.created_count }}</p>
        <div v-if="saveResult.skipped.length" class="max-w-sm text-sm text-fg/60">
          <p class="mb-1 text-amber-700 dark:text-amber-400">Пропущено: {{ saveResult.skipped.length }}</p>
          <ul class="space-y-1 text-left">
            <li v-for="s in saveResult.skipped" :key="s.index">№{{ s.index + 1 }}: {{ s.error }}</li>
          </ul>
        </div>
        <BaseButton @click="emit('close')">Готово</BaseButton>
      </div>
    </div>
  </div>
</template>
