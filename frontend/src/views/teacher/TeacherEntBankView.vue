<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { onMounted } from "vue";

import {
  bulkDeleteEntQuestions,
  createEntSubject,
  createSubjectQuestion,
  deleteEntQuestion,
  deleteEntQuestionImage,
  getEntQuestionImageUrl,
  listSubjectQuestions,
  listTeacherEntSubjects,
  updateEntSubject,
  updateSubjectQuestion,
  uploadEntQuestionImage,
} from "@/api/ent";
import EntPdfImportModal from "@/components/ent/EntPdfImportModal.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import BaseInput from "@/components/ui/BaseInput.vue";
import PaginationControls from "@/components/ui/PaginationControls.vue";
import { useModalFocusTrap } from "@/composables/useModalFocusTrap";
import type { EntQuestionTeacher, EntQuestionType, EntSubject, ExamLanguage } from "@/types";
import { EXAM_LANGUAGES, LANGUAGE_FLAG, LANGUAGE_LABEL } from "@/utils/examLanguage";

// Dense card rows, not table rows -- bigger than the app's usual page size
// of 20 so a teacher isn't clicking through pagination constantly, but
// still well under the backend's 100 cap so the DOM stays light.
const QUESTIONS_PER_PAGE = 50;

const QTYPE_LABEL: Record<EntQuestionType, string> = {
  single: "Один правильный ответ",
  multiple: "Несколько правильных ответов",
  matching: "Сопоставление",
  short_answer: "Краткий ответ",
};

const subjects = ref<EntSubject[]>([]);
const loading = ref(true);
const newSubjectName = ref("");

const openSubjectId = ref<number | null>(null);
const questionsBySubject = reactive<Record<number, EntQuestionTeacher[]>>({});
const questionsLoading = ref(false);
// Pagination state per subject -- more than one subject's questions can be
// cached at once (a teacher expands, collapses, expands another), so this
// can't be a single shared object or switching back to an already-cached
// subject would show the wrong page/total.
const questionsPageBySubject = reactive<Record<number, { page: number; total: number; pages: number }>>({});
function questionsPageFor(subjectId: number) {
  return questionsPageBySubject[subjectId] ?? { page: 1, total: 0, pages: 0 };
}
const editingQuestionId = ref<number | null>(null);

const renamingSubjectId = ref<number | null>(null);
const renameValue = ref("");

const showPdfImportModal = ref(false);

// Which language the bank is showing. "all" is the default: a teacher opens
// this screen to find a question, not to audit one language of it. The
// filtering is done by the API, so a subject with 400 Russian questions does
// not ship them all to draw a Kazakh list.
const bankLanguage = ref<ExamLanguage | "all">("all");

async function loadQuestions(subjectId: number, page = 1) {
  const res = await listSubjectQuestions(
    subjectId,
    bankLanguage.value === "all" ? undefined : bankLanguage.value,
    page,
    QUESTIONS_PER_PAGE,
  );
  questionsBySubject[subjectId] = res.items;
  questionsPageBySubject[subjectId] = { page: res.page, total: res.total, pages: res.pages };
}

async function changeQuestionsPage(subjectId: number, page: number) {
  clearSelection(true);
  questionsLoading.value = true;
  try {
    await loadQuestions(subjectId, page);
  } finally {
    questionsLoading.value = false;
  }
}

// ── Toast: a small local banner, not a global system -- the only screen
// that currently needs one is this one (bulk-delete partial failure,
// single-delete rollback, "selection was reset" notices).
const toast = ref<{ message: string; tone: "error" | "info" } | null>(null);
let toastTimer: ReturnType<typeof setTimeout> | null = null;

function showToast(message: string, tone: "error" | "info" = "info", ms = 4000) {
  if (toastTimer) clearTimeout(toastTimer);
  toast.value = { message, tone };
  toastTimer = setTimeout(() => (toast.value = null), ms);
}

// ── Bulk selection: scoped to whichever subject is currently expanded.
// Cleared (with a notice) whenever the language filter or the open subject
// changes, so a selection never silently carries over onto a different set
// of questions than the one the teacher is looking at.
const selectedIds = reactive(new Set<number>());
const lastClickedIndex = ref<number | null>(null);

function clearSelection(notify = false) {
  if (notify && selectedIds.size > 0) showToast("Выбор сброшен", "info", 2500);
  selectedIds.clear();
  lastClickedIndex.value = null;
}

function toggleQuestionSelection(subjectId: number, index: number, event: MouseEvent) {
  const list = questionsBySubject[subjectId];
  const question = list[index];
  if (event.shiftKey && lastClickedIndex.value !== null) {
    const [start, end] = [lastClickedIndex.value, index].sort((a, b) => a - b);
    for (let i = start; i <= end; i++) selectedIds.add(list[i].id);
  } else if (selectedIds.has(question.id)) {
    selectedIds.delete(question.id);
  } else {
    selectedIds.add(question.id);
  }
  lastClickedIndex.value = index;
}

function visibleQuestions(subjectId: number): EntQuestionTeacher[] {
  return questionsBySubject[subjectId] ?? [];
}

function allVisibleSelected(subjectId: number): boolean {
  const list = visibleQuestions(subjectId);
  return list.length > 0 && list.every((q) => selectedIds.has(q.id));
}

function toggleSelectAllVisible(subjectId: number) {
  const list = visibleQuestions(subjectId);
  if (allVisibleSelected(subjectId)) {
    for (const q of list) selectedIds.delete(q.id);
  } else {
    for (const q of list) selectedIds.add(q.id);
  }
}

const bulkDeleteModalOpen = ref(false);
const bulkDeleteModalRef = ref<HTMLElement | null>(null);
const bulkDeleteConfirmText = ref("");
const bulkDeleting = ref(false);
// Below this count, a plain "are you sure" is enough; above it, the teacher
// has to type the exact number being removed -- the spec's protection
// against an autopilot double-click wiping out a big chunk of the bank.
const TYPED_CONFIRM_THRESHOLD = 10;

const needsTypedConfirm = computed(() => selectedIds.size > TYPED_CONFIRM_THRESHOLD);
const canConfirmBulkDelete = computed(
  () => !needsTypedConfirm.value || bulkDeleteConfirmText.value.trim() === String(selectedIds.size),
);

function openBulkDeleteModal() {
  bulkDeleteConfirmText.value = "";
  bulkDeleteModalOpen.value = true;
}

function closeBulkDeleteModal() {
  if (bulkDeleting.value) return;
  bulkDeleteModalOpen.value = false;
}

useModalFocusTrap(bulkDeleteModalRef, closeBulkDeleteModal);

async function confirmBulkDelete() {
  if (!canConfirmBulkDelete.value || openSubjectId.value === null) return;
  const subjectId = openSubjectId.value;
  const ids = [...selectedIds];

  bulkDeleting.value = true;
  try {
    const result = await bulkDeleteEntQuestions(ids);
    const deleted = new Set(result.deleted);
    questionsBySubject[subjectId] = questionsBySubject[subjectId].filter((q) => !deleted.has(q.id));
    const subject = subjects.value.find((s) => s.id === subjectId);
    if (subject) subject.question_count = Math.max(0, subject.question_count - deleted.size);
    clearSelection();
    bulkDeleteModalOpen.value = false;
    if (result.failed.length > 0) {
      showToast(`Удалено ${deleted.size}, не найдено ${result.failed.length} (уже удалены ранее)`, "info");
    } else {
      showToast(`Удалено вопросов: ${deleted.size}`, "info");
    }
  } catch {
    showToast("Не удалось удалить выбранные вопросы. Попробуйте ещё раз.", "error");
  } finally {
    bulkDeleting.value = false;
  }
}

async function setBankLanguage(value: ExamLanguage | "all") {
  if (bankLanguage.value === value) return;
  bankLanguage.value = value;
  clearSelection(true);
  // Everything cached was fetched under the previous filter.
  for (const key of Object.keys(questionsBySubject)) delete questionsBySubject[Number(key)];
  for (const key of Object.keys(questionsPageBySubject)) delete questionsPageBySubject[Number(key)];
  if (openSubjectId.value !== null) {
    questionsLoading.value = true;
    await loadQuestions(openSubjectId.value);
    questionsLoading.value = false;
  }
}

async function handlePdfImportSaved() {
  // Refresh question counts for whichever subject the import targeted, and
  // its question list if it happened to be expanded.
  await load();
  if (openSubjectId.value !== null) {
    await loadQuestions(openSubjectId.value);
  }
}

const quotaModalSubject = ref<EntSubject | null>(null);
const quotaModalRef = ref<HTMLElement | null>(null);
const quotaForm = reactive({
  single_choice_count: 0,
  multiple_choice_count: 0,
  matching_count: 0,
  short_answer_count: 0,
});
const savingQuotas = ref(false);

function openQuotaModal(subject: EntSubject) {
  quotaModalSubject.value = subject;
  quotaForm.single_choice_count = subject.single_choice_count;
  quotaForm.multiple_choice_count = subject.multiple_choice_count;
  quotaForm.matching_count = subject.matching_count;
  quotaForm.short_answer_count = subject.short_answer_count;
}

function closeQuotaModal() {
  quotaModalSubject.value = null;
}

useModalFocusTrap(quotaModalRef, closeQuotaModal);

async function saveQuotas() {
  if (!quotaModalSubject.value) return;
  savingQuotas.value = true;
  try {
    await updateEntSubject(quotaModalSubject.value.id, { ...quotaForm });
    await load();
    closeQuotaModal();
  } finally {
    savingQuotas.value = false;
  }
}

interface QuestionForm {
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

// The image URL is stable per question, so the browser would keep showing the
// old file after a re-upload -- bump this to bust the cache.
const imageVersion = ref(0);
// Bumped to force a fresh <input type="file">, which can't be cleared via v-model.
const fileInputKey = ref(0);

function questionImageUrl(questionId: number): string {
  return `${getEntQuestionImageUrl(questionId)}?v=${imageVersion.value}`;
}

function blankForm(): QuestionForm {
  return {
    qtype: "single",
    text: "",
    // A new question defaults to whichever language the bank is filtered to,
    // so adding three Kazakh questions in a row doesn't mean setting the
    // dropdown three times.
    language: bankLanguage.value === "all" ? "ru" : bankLanguage.value,
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

const questionForms = reactive<Record<number, QuestionForm>>({});

async function load() {
  loading.value = true;
  subjects.value = await listTeacherEntSubjects();
  loading.value = false;
}

onMounted(load);

async function handleCreateSubject() {
  if (!newSubjectName.value.trim()) return;
  const subject = await createEntSubject({ name: newSubjectName.value });
  newSubjectName.value = "";
  await load();
  // Jump straight to the question form for the subject just created,
  // instead of leaving the teacher to figure out that clicking its
  // name is what reveals it.
  openSubjectId.value = subject.id;
  editingQuestionId.value = null;
  if (!questionForms[subject.id]) questionForms[subject.id] = blankForm();
  await loadQuestions(subject.id);
}

async function handleToggleActive(subject: EntSubject) {
  await updateEntSubject(subject.id, { is_active: !subject.is_active });
  await load();
}

function startRenameSubject(subject: EntSubject) {
  renamingSubjectId.value = subject.id;
  renameValue.value = subject.name;
}

function cancelRenameSubject() {
  renamingSubjectId.value = null;
}

async function handleRenameSubject(subjectId: number) {
  if (!renameValue.value.trim()) return;
  await updateEntSubject(subjectId, { name: renameValue.value.trim() });
  renamingSubjectId.value = null;
  await load();
}

async function toggleSubject(subjectId: number) {
  clearSelection();
  if (openSubjectId.value === subjectId) {
    openSubjectId.value = null;
    return;
  }
  openSubjectId.value = subjectId;
  editingQuestionId.value = null;
  if (!questionForms[subjectId]) questionForms[subjectId] = blankForm();
  if (!questionsBySubject[subjectId]) {
    questionsLoading.value = true;
    await loadQuestions(subjectId);
    questionsLoading.value = false;
  }
}

function startEditQuestion(subjectId: number, question: EntQuestionTeacher) {
  editingQuestionId.value = question.id;
  const fallback = blankForm();
  questionForms[subjectId] = {
    qtype: question.qtype,
    text: question.text,
    language: question.language,
    maxScore: question.max_score,
    imageFile: null,
    hasImage: question.has_image,
    choices: question.choices.length
      ? question.choices.map((c) => ({ text: c.text, isCorrect: c.is_correct }))
      : fallback.choices,
    matchPairs: question.match_pairs.length
      ? question.match_pairs.map((p) => ({ promptText: p.prompt_text, answerText: p.answer_text }))
      : fallback.matchPairs,
    answerVariants: question.answer_variants.length ? question.answer_variants.map((v) => v.text) : [""],
  };
}

function cancelEditQuestion(subjectId: number) {
  editingQuestionId.value = null;
  questionForms[subjectId] = blankForm();
  fileInputKey.value += 1;
}

function onImagePicked(subjectId: number, event: Event) {
  const input = event.target as HTMLInputElement;
  questionForms[subjectId].imageFile = input.files?.[0] ?? null;
}

async function handleRemoveImage(subjectId: number) {
  const form = questionForms[subjectId];
  form.imageFile = null;
  fileInputKey.value += 1;

  // A not-yet-saved pick is dropped locally; an image already on the server
  // needs the question to exist, which only holds while editing.
  if (editingQuestionId.value !== null && form.hasImage) {
    await deleteEntQuestionImage(editingQuestionId.value);
    form.hasImage = false;
    imageVersion.value += 1;
    await loadQuestions(subjectId, questionsPageFor(subjectId).page);
  }
}

function onQtypeChange(subjectId: number) {
  const form = questionForms[subjectId];
  if (form.qtype === "multiple" || form.qtype === "matching") {
    form.maxScore = 2;
  } else if (form.maxScore === 2 && form.qtype !== "single" && form.qtype !== "short_answer") {
    form.maxScore = 1;
  }
}

function addChoice(subjectId: number) {
  const form = questionForms[subjectId];
  if (form.choices.length < 8) form.choices.push({ text: "", isCorrect: false });
}

function addMatchPair(subjectId: number) {
  questionForms[subjectId].matchPairs.push({ promptText: "", answerText: "" });
}

function addAnswerVariant(subjectId: number) {
  questionForms[subjectId].answerVariants.push("");
}

function isFormValid(form: QuestionForm): boolean {
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

async function handleSaveQuestion(subjectId: number) {
  const form = questionForms[subjectId];
  if (!isFormValid(form)) return;

  const payload = {
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
    answer_variants:
      form.qtype === "short_answer" ? form.answerVariants.filter((v) => v.trim()) : undefined,
  };

  // The image rides on the question row, so a brand-new question has to exist
  // before its file can be attached.
  const saved =
    editingQuestionId.value !== null
      ? await updateSubjectQuestion(editingQuestionId.value, payload)
      : await createSubjectQuestion(subjectId, payload);

  if (form.imageFile) {
    await uploadEntQuestionImage(saved.id, form.imageFile);
    imageVersion.value += 1;
  }

  editingQuestionId.value = null;
  questionForms[subjectId] = blankForm();
  fileInputKey.value += 1;
  await loadQuestions(subjectId, questionsPageFor(subjectId).page);
  await load();
}

async function handleDeleteQuestion(subjectId: number, questionId: number) {
  // Optimistic: remove locally first, roll back to the same spot on
  // failure. No full subjects/questions refetch either way -- that was
  // what collapsed the list's height and reset scroll position before.
  const list = questionsBySubject[subjectId];
  const index = list.findIndex((q) => q.id === questionId);
  if (index === -1) return;
  const [removed] = list.splice(index, 1);
  selectedIds.delete(questionId);
  const subject = subjects.value.find((s) => s.id === subjectId);
  if (subject) subject.question_count = Math.max(0, subject.question_count - 1);
  if (editingQuestionId.value === questionId) cancelEditQuestion(subjectId);

  try {
    await deleteEntQuestion(questionId);
  } catch {
    list.splice(index, 0, removed);
    if (subject) subject.question_count += 1;
    showToast("Не удалось удалить вопрос", "error");
  }
}
</script>

<template>
  <div>
    <h1 class="mb-2 text-2xl font-semibold">Банк вопросов ЕНТ-симулятора</h1>
    <p class="mb-6 text-sm text-fg/60">
      Сначала добавьте предмет, затем откройте его карточку кнопкой «Вопросы» — там же добавляются и редактируются
      вопросы всех типов (один/несколько ответов, сопоставление, короткий ответ).
    </p>

    <form
      class="mb-6 flex flex-col gap-3 rounded-xl border border-fg/10 p-4 sm:flex-row sm:items-end"
      @submit.prevent="handleCreateSubject"
    >
      <BaseInput v-model="newSubjectName" label="Новый предмет" class="flex-1" />
      <BaseButton type="submit">Добавить предмет</BaseButton>
      <BaseButton
        type="button"
        variant="secondary"
        :disabled="!subjects.length"
        @click="showPdfImportModal = true"
      >
        Импорт из PDF
      </BaseButton>
    </form>

    <EntPdfImportModal
      v-if="showPdfImportModal"
      :subjects="subjects"
      :initial-subject-id="openSubjectId"
      @close="showPdfImportModal = false"
      @saved="handlePdfImportSaved"
    />

    <p v-if="loading" class="text-fg/60">Загрузка…</p>

    <div v-else class="space-y-4">
      <div v-for="subject in subjects" :key="subject.id" class="rounded-xl border border-fg/10 p-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex flex-1 items-center gap-2">
            <template v-if="renamingSubjectId === subject.id">
              <input
                v-model="renameValue"
                class="rounded-lg border border-fg/20 bg-transparent px-2 py-1 text-lg font-medium"
                @keyup.enter="handleRenameSubject(subject.id)"
                @keyup.escape="cancelRenameSubject"
              />
              <BaseButton @click="handleRenameSubject(subject.id)">Сохранить</BaseButton>
              <BaseButton variant="secondary" @click="cancelRenameSubject">Отмена</BaseButton>
            </template>
            <template v-else>
              <span class="text-lg font-medium">{{ subject.name }}</span>
              <button class="text-sm text-fg/50 hover:text-fg" @click="startRenameSubject(subject)">
                Переименовать
              </button>
              <BaseBadge tone="neutral">{{ subject.question_count }} вопросов</BaseBadge>
              <BaseBadge v-if="subject.question_count > 0" tone="neutral">
                🇷🇺 {{ subject.ru_count }} / 🇰🇿 {{ subject.kk_count }}
              </BaseBadge>
              <BaseBadge :tone="subject.is_active ? 'success' : 'warning'">
                {{ subject.is_active ? "активен" : "скрыт" }}
              </BaseBadge>
              <BaseBadge
                v-if="
                  subject.single_choice_count +
                    subject.multiple_choice_count +
                    subject.matching_count +
                    subject.short_answer_count >
                  0
                "
                tone="neutral"
              >
                квоты: {{ subject.single_choice_count }}/{{ subject.multiple_choice_count }}/{{
                  subject.matching_count
                }}/{{ subject.short_answer_count }}
              </BaseBadge>
            </template>
          </div>
          <BaseButton variant="secondary" @click="toggleSubject(subject.id)">
            {{ openSubjectId === subject.id ? "Свернуть" : "Вопросы" }}
          </BaseButton>
          <BaseButton variant="secondary" @click="openQuotaModal(subject)">Настроить структуру</BaseButton>
          <BaseButton variant="secondary" @click="handleToggleActive(subject)">
            {{ subject.is_active ? "Скрыть" : "Показать" }}
          </BaseButton>
        </div>

        <div v-if="openSubjectId === subject.id" class="mt-4 space-y-4 border-t border-fg/10 pt-4">
          <!-- ── Language tabs: filter the bank itself, server-side ────── -->
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-xs text-fg/50">Язык вопросов:</span>
            <button
              type="button"
              class="rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-150"
              :class="
                bankLanguage === 'all'
                  ? 'bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-500/25'
                  : 'bg-fg/5 text-fg/60 hover:bg-fg/10 hover:text-fg'
              "
              @click="setBankLanguage('all')"
            >
              Все
            </button>
            <button
              v-for="language in EXAM_LANGUAGES"
              :key="language"
              type="button"
              class="rounded-xl px-3 py-1.5 text-xs font-medium transition-all duration-150"
              :class="
                bankLanguage === language
                  ? 'bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-500/25'
                  : 'bg-fg/5 text-fg/60 hover:bg-fg/10 hover:text-fg'
              "
              @click="setBankLanguage(language)"
            >
              {{ LANGUAGE_FLAG[language] }} Только {{ LANGUAGE_LABEL[language] }}
            </button>
          </div>

          <!-- Only the very first open of a subject shows the plain loading
               text (nothing to keep on screen yet). A page change keeps the
               existing list mounted -- dimmed, not removed -- so the
               document height never collapses and the scroll position never
               gets reclamped to a shorter page. -->
          <p v-if="questionsLoading && !questionsBySubject[subject.id]" class="text-sm text-fg/60">
            Загрузка вопросов…
          </p>
          <template v-else>
            <div
              :class="{ 'pointer-events-none opacity-50 transition-opacity duration-150': questionsLoading }"
            >
              <div v-if="questionsBySubject[subject.id]?.length" class="flex items-center gap-2 text-sm text-fg/60">
                <input
                  type="checkbox"
                  :checked="allVisibleSelected(subject.id)"
                  aria-label="Выбрать все вопросы на экране"
                  @click.stop="toggleSelectAllVisible(subject.id)"
                />
                <span>Выбрать все на этом экране ({{ questionsBySubject[subject.id].length }})</span>
                <span
                  v-if="questionsPageFor(subject.id).total > questionsBySubject[subject.id].length"
                  class="text-fg/40"
                >
                  из {{ questionsPageFor(subject.id).total }} по текущему фильтру
                </span>
              </div>

              <!-- ── Sticky bulk-action bar: only takes space once something is selected ── -->
              <div
                v-if="selectedIds.size > 0"
                class="sticky top-2 z-10 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-indigo-500/30 bg-indigo-500/10 px-3 py-2 text-sm"
              >
                <span class="font-medium">Выбрано: {{ selectedIds.size }}</span>
                <div class="flex items-center gap-2">
                  <button type="button" class="text-fg/60 hover:text-fg" @click="clearSelection()">Снять выбор</button>
                  <BaseButton variant="danger" :disabled="selectedIds.size === 0" @click="openBulkDeleteModal">
                    Удалить выбранные ({{ selectedIds.size }})
                  </BaseButton>
                </div>
              </div>

              <ul class="space-y-2">
                <li
                  v-for="(q, index) in questionsBySubject[subject.id]"
                  :key="q.id"
                  class="flex items-start justify-between gap-3 rounded-lg border border-fg/10 p-3 text-sm"
                  :class="{ 'border-indigo-500/50 bg-indigo-500/5': selectedIds.has(q.id) }"
                >
                  <div class="flex min-w-0 gap-3">
                    <input
                      type="checkbox"
                      class="mt-1 shrink-0"
                      :checked="selectedIds.has(q.id)"
                      :aria-label="`Выбрать вопрос: ${q.text}`"
                      @click.stop="toggleQuestionSelection(subject.id, index, $event)"
                    />
                    <img
                      v-if="q.has_image"
                      :src="questionImageUrl(q.id)"
                      alt=""
                      class="h-16 w-24 shrink-0 rounded-lg border border-fg/10 object-cover"
                    />
                    <div class="min-w-0">
                      <BaseBadge tone="neutral">{{ LANGUAGE_FLAG[q.language] }} {{ LANGUAGE_LABEL[q.language] }}</BaseBadge>
                      <BaseBadge tone="neutral">{{ QTYPE_LABEL[q.qtype] }}</BaseBadge>
                      <BaseBadge tone="neutral">{{ q.max_score }} балл(а)</BaseBadge>
                      <p class="mt-1">{{ q.text }}</p>
                    </div>
                  </div>
                  <div class="flex shrink-0 gap-2">
                    <BaseButton variant="secondary" @click="startEditQuestion(subject.id, q)">Редактировать</BaseButton>
                    <button
                      type="button"
                      class="rounded-lg p-2 text-zinc-400 transition-colors hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-500/10"
                      aria-label="Удалить вопрос"
                      title="Удалить вопрос"
                      @click="handleDeleteQuestion(subject.id, q.id)"
                    >
                      🗑
                    </button>
                  </div>
                </li>
                <li v-if="!questionsBySubject[subject.id]?.length" class="text-sm text-fg/60">
                  {{
                    bankLanguage === "all"
                      ? "Вопросов пока нет."
                      : `Вопросов на языке «${LANGUAGE_LABEL[bankLanguage]}» пока нет.`
                  }}
                </li>
              </ul>
            </div>

            <PaginationControls
              :page="questionsPageFor(subject.id).page"
              :pages="questionsPageFor(subject.id).pages"
              :total="questionsPageFor(subject.id).total"
              @change="changeQuestionsPage(subject.id, $event)"
            />
          </template>

          <div class="space-y-3 rounded-lg bg-fg/5 p-4">
            <p class="text-sm font-medium">
              {{ editingQuestionId !== null ? "Редактирование вопроса" : "Новый вопрос" }}
            </p>

            <label class="block text-sm">
              <span class="mb-1.5 block font-medium text-fg/80">Тип вопроса</span>
              <select
                v-model="questionForms[subject.id].qtype"
                class="w-full rounded-lg border border-border bg-card px-4 py-2.5 text-sm text-fg"
                @change="onQtypeChange(subject.id)"
              >
                <option v-for="(label, value) in QTYPE_LABEL" :key="value" :value="value">{{ label }}</option>
              </select>
            </label>

            <label class="block text-sm">
              <span class="mb-1.5 block font-medium text-fg/80">Язык вопроса</span>
              <select
                v-model="questionForms[subject.id].language"
                class="w-full rounded-lg border border-border bg-card px-4 py-2.5 text-sm text-fg"
              >
                <option v-for="language in EXAM_LANGUAGES" :key="language" :value="language">
                  {{ LANGUAGE_FLAG[language] }} {{ LANGUAGE_LABEL[language] }}
                </option>
              </select>
            </label>

            <BaseInput v-model="questionForms[subject.id].text" label="Текст вопроса" />

            <div class="text-sm">
              <span class="mb-1.5 block font-medium text-fg/80">Изображение к вопросу (необязательно)</span>
              <div class="flex flex-wrap items-center gap-3">
                <img
                  v-if="questionForms[subject.id].hasImage && editingQuestionId !== null"
                  :src="questionImageUrl(editingQuestionId)"
                  alt=""
                  class="h-20 w-28 rounded-lg border border-fg/10 object-cover"
                />
                <input
                  :key="fileInputKey"
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  class="text-sm text-fg/70 file:mr-3 file:rounded-lg file:border-0 file:bg-fg/10 file:px-3 file:py-2 file:text-sm file:text-fg hover:file:bg-fg/15"
                  @change="onImagePicked(subject.id, $event)"
                />
                <BaseButton
                  v-if="questionForms[subject.id].imageFile || questionForms[subject.id].hasImage"
                  variant="secondary"
                  @click="handleRemoveImage(subject.id)"
                >
                  Убрать изображение
                </BaseButton>
              </div>
              <p v-if="questionForms[subject.id].imageFile" class="mt-1.5 text-xs text-fg/50">
                Выбрано: {{ questionForms[subject.id].imageFile?.name }} — загрузится при сохранении вопроса.
              </p>
              <p class="mt-1.5 text-xs text-fg/50">jpg, png или webp, до 5 МБ.</p>
            </div>

            <label class="block text-sm" v-if="questionForms[subject.id].qtype !== 'multiple' && questionForms[subject.id].qtype !== 'matching'">
              <span class="mb-1.5 block font-medium text-fg/80">Баллы за вопрос</span>
              <select
                v-model.number="questionForms[subject.id].maxScore"
                class="w-full rounded-lg border border-border bg-card px-4 py-2.5 text-sm text-fg"
              >
                <option :value="1">1</option>
                <option :value="2">2 (профильный)</option>
              </select>
            </label>
            <p v-else class="text-sm text-fg/60">Баллы: 2 (2 — всё верно, 1 — частично, 0 — иначе)</p>

            <template v-if="questionForms[subject.id].qtype === 'single' || questionForms[subject.id].qtype === 'multiple'">
              <div v-for="(choice, i) in questionForms[subject.id].choices" :key="i" class="flex items-center gap-2">
                <input
                  v-if="questionForms[subject.id].qtype === 'single'"
                  type="radio"
                  :name="`correct-${subject.id}`"
                  :checked="choice.isCorrect"
                  @change="questionForms[subject.id].choices.forEach((c, ci) => (c.isCorrect = ci === i))"
                />
                <input v-else type="checkbox" v-model="choice.isCorrect" />
                <input
                  v-model="choice.text"
                  placeholder="Вариант ответа"
                  class="flex-1 rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm"
                />
              </div>
              <BaseButton variant="secondary" @click="addChoice(subject.id)">+ вариант</BaseButton>
            </template>

            <template v-else-if="questionForms[subject.id].qtype === 'matching'">
              <div v-for="(pair, i) in questionForms[subject.id].matchPairs" :key="i" class="flex items-center gap-2">
                <input
                  v-model="pair.promptText"
                  placeholder="Слева (вопрос)"
                  class="flex-1 rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm"
                />
                <input
                  v-model="pair.answerText"
                  placeholder="Справа (правильная пара)"
                  class="flex-1 rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm"
                />
              </div>
              <BaseButton variant="secondary" @click="addMatchPair(subject.id)">+ пара</BaseButton>
            </template>

            <template v-else>
              <div v-for="(_, i) in questionForms[subject.id].answerVariants" :key="i" class="flex items-center gap-2">
                <input
                  v-model="questionForms[subject.id].answerVariants[i]"
                  placeholder="Принимаемый ответ"
                  class="flex-1 rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm"
                />
              </div>
              <BaseButton variant="secondary" @click="addAnswerVariant(subject.id)">+ вариант написания</BaseButton>
            </template>

            <div class="flex gap-2">
              <BaseButton :disabled="!isFormValid(questionForms[subject.id])" @click="handleSaveQuestion(subject.id)">
                {{ editingQuestionId !== null ? "Сохранить изменения" : "Сохранить вопрос" }}
              </BaseButton>
              <BaseButton v-if="editingQuestionId !== null" variant="secondary" @click="cancelEditQuestion(subject.id)">
                Отмена
              </BaseButton>
            </div>
          </div>
        </div>
      </div>
      <p v-if="!subjects.length" class="text-fg/60">Пока нет ни одного предмета.</p>
    </div>

    <!-- ── Subject structure (qtype quota) modal ─────────────────────── -->
    <div
      v-if="quotaModalSubject"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      @click.self="closeQuotaModal"
    >
      <div ref="quotaModalRef" role="dialog" aria-modal="true" class="w-full max-w-md rounded-2xl border border-border bg-card p-5">
        <h2 class="mb-1 text-lg font-semibold">Структура предмета «{{ quotaModalSubject.name }}»</h2>
        <p class="mb-4 text-sm text-fg/60">
          Сколько вопросов каждого типа брать при генерации симуляции. Если всё оставить по 0, предмет останется в
          старом режиме — случайная выборка без учёта типа.
        </p>

        <div class="space-y-3">
          <label class="block text-sm">
            <span class="mb-1.5 block font-medium text-fg/80">Один правильный ответ (single choice)</span>
            <input
              v-model.number="quotaForm.single_choice_count"
              type="number"
              min="0"
              max="100"
              class="w-full rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm"
            />
          </label>
          <label class="block text-sm">
            <span class="mb-1.5 block font-medium text-fg/80">Несколько правильных ответов (multiple choice)</span>
            <input
              v-model.number="quotaForm.multiple_choice_count"
              type="number"
              min="0"
              max="100"
              class="w-full rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm"
            />
          </label>
          <label class="block text-sm">
            <span class="mb-1.5 block font-medium text-fg/80">Сопоставление (matching)</span>
            <input
              v-model.number="quotaForm.matching_count"
              type="number"
              min="0"
              max="100"
              class="w-full rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm"
            />
          </label>
          <label class="block text-sm">
            <span class="mb-1.5 block font-medium text-fg/80">Краткий ответ (short answer)</span>
            <input
              v-model.number="quotaForm.short_answer_count"
              type="number"
              min="0"
              max="100"
              class="w-full rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm"
            />
          </label>
        </div>

        <div class="mt-5 flex justify-end gap-2">
          <BaseButton variant="secondary" :disabled="savingQuotas" @click="closeQuotaModal">Отмена</BaseButton>
          <BaseButton :disabled="savingQuotas" @click="saveQuotas">Сохранить</BaseButton>
        </div>
      </div>
    </div>

    <!-- ── Bulk-delete confirmation. No backdrop-click close: this is the one
         action in this screen that can wipe out real work, so closing it
         has to be a deliberate click, not a stray click near the edge. ── -->
    <div v-if="bulkDeleteModalOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        ref="bulkDeleteModalRef"
        role="dialog"
        aria-modal="true"
        class="w-full max-w-md rounded-2xl border border-border bg-card p-5"
      >
        <h2 class="mb-1 text-lg font-semibold">Удалить выбранные вопросы?</h2>
        <p class="mb-4 text-sm text-fg/60">
          Будет удалено вопросов: <strong>{{ selectedIds.size }}</strong
          >. Это действие нельзя отменить.
        </p>

        <label v-if="needsTypedConfirm" class="mb-4 block text-sm">
          <span class="mb-1.5 block font-medium text-fg/80">
            Введите количество удаляемых вопросов ({{ selectedIds.size }}) для подтверждения
          </span>
          <input
            v-model="bulkDeleteConfirmText"
            type="text"
            inputmode="numeric"
            class="w-full rounded-lg border border-fg/20 bg-card px-3 py-2 text-sm text-fg"
            @keyup.enter="canConfirmBulkDelete && confirmBulkDelete()"
          />
        </label>

        <div class="flex justify-end gap-2">
          <BaseButton variant="secondary" :disabled="bulkDeleting" @click="closeBulkDeleteModal">Отмена</BaseButton>
          <!-- Not autofocused on purpose: an accidental Enter shouldn't delete. -->
          <BaseButton variant="danger" :disabled="!canConfirmBulkDelete || bulkDeleting" @click="confirmBulkDelete">
            {{ bulkDeleting ? "Удаление…" : `Удалить (${selectedIds.size})` }}
          </BaseButton>
        </div>
      </div>
    </div>

    <!-- ── Toast ──────────────────────────────────────────────────────── -->
    <div
      v-if="toast"
      class="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-lg px-4 py-2.5 text-sm shadow-lg"
      :class="toast.tone === 'error' ? 'bg-red-600 text-white' : 'bg-fg text-bg'"
      role="status"
    >
      {{ toast.message }}
    </div>
  </div>
</template>
