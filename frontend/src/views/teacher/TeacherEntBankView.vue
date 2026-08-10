<script setup lang="ts">
import { Eye, EyeOff, Pencil, Plus, Search, SlidersHorizontal, Trash2, UploadCloud } from "@lucide/vue";
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
import EntQuestionForm from "@/components/ent/EntQuestionForm.vue";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import PaginationControls from "@/components/ui/PaginationControls.vue";
import { useModalFocusTrap } from "@/composables/useModalFocusTrap";
import type { EntQuestionTeacher, EntQuestionType, EntSubject, ExamLanguage } from "@/types";
import { blankQuestionForm, buildEntQuestionPayload, isQuestionFormValid, type QuestionForm } from "@/utils/entQuestionForm";
import { EXAM_LANGUAGES, LANGUAGE_LABEL } from "@/utils/examLanguage";

// Dense card rows, not table rows -- bigger than the app's usual page size
// of 20 so a teacher isn't clicking through pagination constantly, but
// still well under the backend's 100 cap so the DOM stays light.
const QUESTIONS_PER_PAGE = 50;

// Short form for the question-card badges (the select above uses the fuller
// wording; the card is dense and only has room for a couple of words).
const QTYPE_BADGE: Record<EntQuestionType, string> = {
  single: "Одиночный выбор",
  multiple: "Множественный выбор",
  matching: "Сопоставление",
  short_answer: "Краткий ответ",
};

const LANG_BADGE: Record<ExamLanguage, string> = {
  ru: "RU",
  kk: "KZ",
};

const subjects = ref<EntSubject[]>([]);
const loading = ref(true);
const newSubjectName = ref("");

const openSubjectId = ref<number | null>(null);
const selectedSubject = computed(() => subjects.value.find((s) => s.id === openSubjectId.value) ?? null);

function hasQuotas(subject: EntSubject): boolean {
  return (
    subject.single_choice_count + subject.multiple_choice_count + subject.matching_count + subject.short_answer_count >
    0
  );
}

const questionsBySubject = reactive<Record<number, EntQuestionTeacher[]>>({});
const questionsLoading = ref(false);
// Pagination state per subject -- more than one subject's questions can be
// cached at once (a teacher switches between subjects in the sidebar), so
// this can't be a single shared object or switching back to an
// already-cached subject would show the wrong page/total.
const questionsPageBySubject = reactive<Record<number, { page: number; total: number; pages: number }>>({});
function questionsPageFor(subjectId: number) {
  return questionsPageBySubject[subjectId] ?? { page: 1, total: 0, pages: 0 };
}
// Which question is being edited in place (its card swaps its display for
// `editForm`), and the form data for it -- separate from `questionForms`
// (the always-visible "new question" form at the bottom of the list) so
// opening an edit never clobbers whatever the teacher was drafting there.
const editingQuestionId = ref<number | null>(null);
const editForm = ref<QuestionForm | null>(null);
const editFileInputKey = ref(0);

const renamingSubjectId = ref<number | null>(null);
const renameValue = ref("");

const showPdfImportModal = ref(false);

// Which language the bank is showing. "all" is the default: a teacher opens
// this screen to find a question, not to audit one language of it. The
// filtering is done by the API, so a subject with 400 Russian questions does
// not ship them all to draw a Kazakh list.
const bankLanguage = ref<ExamLanguage | "all">("all");

// Client-side filter over whatever page is currently loaded -- there is no
// search endpoint, so this narrows what's on screen rather than querying
// the whole bank.
const searchQuery = ref("");
const filteredQuestions = computed<EntQuestionTeacher[]>(() => {
  if (!selectedSubject.value) return [];
  const list = questionsBySubject[selectedSubject.value.id] ?? [];
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return list;
  return list.filter((item) => item.text.toLowerCase().includes(q));
});

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

// ── Bulk selection: scoped to whichever subject is currently open in the
// main panel. Cleared (with a notice) whenever the language filter or the
// open subject changes, so a selection never silently carries over onto a
// different set of questions than the one the teacher is looking at.
const selectedIds = reactive(new Set<number>());
const lastClickedIndex = ref<number | null>(null);

function clearSelection(notify = false) {
  if (notify && selectedIds.size > 0) showToast("Выбор сброшен", "info", 2500);
  selectedIds.clear();
  lastClickedIndex.value = null;
}

// Indexed against `filteredQuestions` (what's actually on screen), so a
// shift-click range and "select all" only ever touch visible rows -- a
// search that's hiding most of the list shouldn't let "select all" sweep up
// questions the teacher can't currently see.
function toggleQuestionSelection(index: number, event: MouseEvent) {
  const list = filteredQuestions.value;
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

function allVisibleSelected(): boolean {
  const list = filteredQuestions.value;
  return list.length > 0 && list.every((q) => selectedIds.has(q.id));
}

function toggleSelectAllVisible() {
  const list = filteredQuestions.value;
  if (allVisibleSelected()) {
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
    const removedQuestions = questionsBySubject[subjectId].filter((q) => deleted.has(q.id));
    questionsBySubject[subjectId] = questionsBySubject[subjectId].filter((q) => !deleted.has(q.id));
    const byLanguage: Partial<Record<ExamLanguage, number>> = {};
    for (const q of removedQuestions) byLanguage[q.language] = (byLanguage[q.language] ?? 0) + 1;
    adjustQuestionTotals(subjectId, byLanguage);
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
  searchQuery.value = "";
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

// The image URL is stable per question, so the browser would keep showing the
// old file after a re-upload -- bump this to bust the cache.
const imageVersion = ref(0);
// Bumped to force a fresh <input type="file">, which can't be cleared via v-model.
const fileInputKey = ref(0);

function questionImageUrl(questionId: number): string {
  return `${getEntQuestionImageUrl(questionId)}?v=${imageVersion.value}`;
}

// A new question defaults to whichever language the bank is filtered to, so
// adding three Kazakh questions in a row doesn't mean setting the dropdown
// three times.
function newQuestionForm(): QuestionForm {
  return blankQuestionForm(bankLanguage.value === "all" ? "ru" : bankLanguage.value);
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
  cancelEditQuestion();
  if (!questionForms[subject.id]) questionForms[subject.id] = newQuestionForm();
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

async function selectSubject(subjectId: number) {
  clearSelection();
  searchQuery.value = "";
  if (openSubjectId.value === subjectId) return;
  openSubjectId.value = subjectId;
  cancelEditQuestion();
  if (!questionForms[subjectId]) questionForms[subjectId] = newQuestionForm();
  if (!questionsBySubject[subjectId]) {
    questionsLoading.value = true;
    await loadQuestions(subjectId);
    questionsLoading.value = false;
  }
}

// ── In-place question editing ─────────────────────────────────────────────
// The card itself becomes the form (see the template): no separate editor
// panel, and critically, nothing scrolls the page to reach it -- the whole
// point is that a click on a card near the top of a long list doesn't dump
// the teacher at the bottom of the page.
function startEditQuestion(question: EntQuestionTeacher) {
  editingQuestionId.value = question.id;
  const fallback = blankQuestionForm(question.language);
  editForm.value = {
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

function cancelEditQuestion() {
  editingQuestionId.value = null;
  editForm.value = null;
  editFileInputKey.value += 1;
}

function onNewImagePicked(subjectId: number, file: File | null) {
  questionForms[subjectId].imageFile = file;
}

function onEditImagePicked(file: File | null) {
  if (editForm.value) editForm.value.imageFile = file;
}

async function handleRemoveNewImage(subjectId: number) {
  questionForms[subjectId].imageFile = null;
  fileInputKey.value += 1;
}

async function handleRemoveEditImage(subjectId: number) {
  if (!editForm.value || editingQuestionId.value === null) return;
  const form = editForm.value;
  const questionId = editingQuestionId.value;
  form.imageFile = null;
  editFileInputKey.value += 1;

  // A not-yet-saved pick is dropped locally; an image already on the server
  // needs a DELETE of its own.
  if (form.hasImage) {
    await deleteEntQuestionImage(questionId);
    form.hasImage = false;
    imageVersion.value += 1;
    await loadQuestions(subjectId, questionsPageFor(subjectId).page);
  }
}

async function handleCreateQuestion(subjectId: number) {
  const form = questionForms[subjectId];
  if (!isQuestionFormValid(form)) return;

  const saved = await createSubjectQuestion(subjectId, buildEntQuestionPayload(form));
  if (form.imageFile) {
    await uploadEntQuestionImage(saved.id, form.imageFile);
    imageVersion.value += 1;
  }

  questionForms[subjectId] = newQuestionForm();
  fileInputKey.value += 1;
  await loadQuestions(subjectId, questionsPageFor(subjectId).page);
  await load();
}

async function handleUpdateQuestion(subjectId: number) {
  if (editingQuestionId.value === null || !editForm.value) return;
  const form = editForm.value;
  if (!isQuestionFormValid(form)) return;
  const questionId = editingQuestionId.value;

  const saved = await updateSubjectQuestion(questionId, buildEntQuestionPayload(form));
  if (form.imageFile) {
    await uploadEntQuestionImage(saved.id, form.imageFile);
    imageVersion.value += 1;
  }

  editingQuestionId.value = null;
  editForm.value = null;
  await loadQuestions(subjectId, questionsPageFor(subjectId).page);
  await load();
}

function adjustQuestionTotals(subjectId: number, byLanguage: Partial<Record<ExamLanguage, number>>) {
  const subject = subjects.value.find((s) => s.id === subjectId);
  const removedCount = Object.values(byLanguage).reduce((sum, n) => sum + (n ?? 0), 0);
  if (subject) {
    subject.question_count = Math.max(0, subject.question_count - removedCount);
    subject.ru_count = Math.max(0, subject.ru_count - (byLanguage.ru ?? 0));
    subject.kk_count = Math.max(0, subject.kk_count - (byLanguage.kk ?? 0));
  }
  const page = questionsPageBySubject[subjectId];
  if (page) {
    page.total = Math.max(0, page.total - removedCount);
    page.pages = Math.max(1, Math.ceil(page.total / QUESTIONS_PER_PAGE));
  }
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
  adjustQuestionTotals(subjectId, { [removed.language]: 1 });
  if (editingQuestionId.value === questionId) cancelEditQuestion();

  try {
    await deleteEntQuestion(questionId);
  } catch {
    list.splice(index, 0, removed);
    adjustQuestionTotals(subjectId, { [removed.language]: -1 });
    showToast("Не удалось удалить вопрос", "error");
  }
}

// A saved question with no markable answer (no correct choice ticked, fewer
// than two matching pairs, no accepted short-answer text) is a genuine
// "needs review" state -- it would score nothing for a student who reaches
// it, most likely because a PDF import saved it with its answer key still
// missing. This is the one legitimate `.marker-edge` case in this view.
function questionNeedsReview(q: EntQuestionTeacher): boolean {
  if (q.qtype === "single" || q.qtype === "multiple") return !q.choices.some((c) => c.is_correct);
  if (q.qtype === "matching") return q.match_pairs.length < 2;
  return q.answer_variants.length === 0;
}

function questionCardClass(q: EntQuestionTeacher): string {
  if (editingQuestionId.value === q.id) return "border-moss ring-1 ring-moss/40";
  if (selectedIds.has(q.id)) return "border-moss/50 bg-moss/10";
  if (questionNeedsReview(q)) return "marker-edge hover:border-line-strong";
  return "hover:border-line-strong";
}
</script>

<template>
  <PageContainer>
    <PageHeader
      title="Банк вопросов ЕНТ-симулятора"
      subtitle="Выберите предмет слева, затем добавляйте и редактируйте вопросы всех типов — один/несколько ответов, сопоставление, короткий ответ."
    />

    <EntPdfImportModal
      v-if="showPdfImportModal"
      :subjects="subjects"
      :initial-subject-id="openSubjectId"
      @close="showPdfImportModal = false"
      @saved="handlePdfImportSaved"
    />

    <div v-if="loading" class="flex flex-col gap-6 lg:flex-row lg:items-start">
      <div class="w-full shrink-0 lg:w-80">
        <div class="h-72 animate-pulse rounded-xl bg-paper-2" />
      </div>
      <div class="min-w-0 flex-1 space-y-3">
        <div class="h-40 animate-pulse rounded-xl bg-paper-2" />
        <div class="h-24 animate-pulse rounded-xl bg-paper-2" />
        <div class="h-24 animate-pulse rounded-xl bg-paper-2" />
      </div>
    </div>

    <div v-else class="flex flex-col gap-6 lg:flex-row lg:items-start">
      <!-- ── Sidebar: subject list + switcher ─────────────────────────── -->
      <aside class="w-full shrink-0 lg:w-80">
        <div class="card p-4">
          <form class="mb-3 flex items-center gap-2" @submit.prevent="handleCreateSubject">
            <input v-model="newSubjectName" placeholder="Новый предмет" class="input min-h-11 min-w-0 flex-1" />
            <button
              type="submit"
              class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-moss text-moss-fg transition-colors hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="!newSubjectName.trim()"
              aria-label="Добавить предмет"
              title="Добавить предмет"
            >
              <Plus :size="18" :stroke-width="2" />
            </button>
          </form>

          <BaseButton
            variant="secondary"
            type="button"
            class="mb-4 w-full"
            :disabled="!subjects.length"
            @click="showPdfImportModal = true"
          >
            <UploadCloud :size="16" :stroke-width="1.8" />
            Импорт из PDF
          </BaseButton>

          <div class="space-y-1">
            <button
              v-for="subject in subjects"
              :key="subject.id"
              type="button"
              class="flex min-h-11 w-full items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-left text-sm transition-colors"
              :class="openSubjectId === subject.id ? 'bg-paper-2 text-ink' : 'text-ink-2 hover:bg-paper-2'"
              @click="selectSubject(subject.id)"
            >
              <span class="flex min-w-0 items-center gap-2">
                <span
                  class="h-1.5 w-1.5 shrink-0 rounded-full"
                  :class="subject.is_active ? 'bg-moss' : 'bg-line-strong'"
                />
                <span class="truncate font-medium">{{ subject.name }}</span>
              </span>
              <span class="shrink-0 text-xs text-ink-3">{{ subject.question_count }}</span>
            </button>
            <p v-if="!subjects.length" class="px-1 py-2 text-sm text-ink-2">
              Пока нет ни одного предмета.
            </p>
          </div>
        </div>
      </aside>

      <!-- ── Main panel ────────────────────────────────────────────────── -->
      <section class="min-w-0 flex-1 space-y-4">
        <div
          v-if="!selectedSubject"
          class="flex h-64 items-center justify-center rounded-xl border border-dashed border-line text-sm text-ink-3"
        >
          Выберите предмет слева
        </div>

        <template v-else>
          <!-- Subject control panel -->
          <div class="card p-5">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <div class="flex min-w-0 flex-1 items-center gap-2">
                <template v-if="renamingSubjectId === selectedSubject.id">
                  <input
                    v-model="renameValue"
                    class="input min-h-11 w-auto px-2 py-1 text-lg font-medium"
                    @keyup.enter="handleRenameSubject(selectedSubject.id)"
                    @keyup.escape="cancelRenameSubject"
                  />
                  <BaseButton @click="handleRenameSubject(selectedSubject.id)">Сохранить</BaseButton>
                  <BaseButton variant="secondary" @click="cancelRenameSubject">Отмена</BaseButton>
                </template>
                <template v-else>
                  <h2 class="truncate text-lg font-semibold text-ink">
                    {{ selectedSubject.name }}
                  </h2>
                  <button
                    class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-paper-2 hover:text-ink"
                    aria-label="Переименовать предмет"
                    title="Переименовать"
                    @click="startRenameSubject(selectedSubject)"
                  >
                    <Pencil :size="14" :stroke-width="1.8" />
                  </button>
                </template>
              </div>
              <div class="flex shrink-0 items-center gap-2">
                <button
                  class="flex min-h-11 items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-paper-2 hover:text-ink"
                  @click="openQuotaModal(selectedSubject)"
                >
                  <SlidersHorizontal :size="14" :stroke-width="1.8" />
                  Структура
                </button>
                <button
                  class="flex min-h-11 items-center gap-1.5 rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-paper-2 hover:text-ink"
                  @click="handleToggleActive(selectedSubject)"
                >
                  <Eye v-if="selectedSubject.is_active" :size="14" :stroke-width="1.8" />
                  <EyeOff v-else :size="14" :stroke-width="1.8" />
                  {{ selectedSubject.is_active ? "Активен" : "Скрыт" }}
                </button>
              </div>
            </div>

            <div class="mt-3 flex flex-wrap items-center gap-2 text-xs">
              <BaseBadge tone="neutral">RU {{ selectedSubject.ru_count }}</BaseBadge>
              <BaseBadge tone="neutral">KZ {{ selectedSubject.kk_count }}</BaseBadge>
              <BaseBadge v-if="hasQuotas(selectedSubject)" tone="neutral">
                квоты {{ selectedSubject.single_choice_count }}/{{ selectedSubject.multiple_choice_count }}/{{
                  selectedSubject.matching_count
                }}/{{ selectedSubject.short_answer_count }}
              </BaseBadge>
            </div>

            <!-- ── Language filter: strict text toggles ─────────────────── -->
            <div class="mt-4 inline-flex overflow-hidden rounded-lg border border-line">
              <button
                type="button"
                class="min-h-11 px-3 py-1.5 text-xs font-medium transition-colors"
                :class="bankLanguage === 'all' ? 'bg-moss text-moss-fg' : 'bg-transparent text-ink-2 hover:bg-paper-2'"
                @click="setBankLanguage('all')"
              >
                Все
              </button>
              <button
                v-for="language in EXAM_LANGUAGES"
                :key="language"
                type="button"
                class="min-h-11 border-l border-line px-3 py-1.5 text-xs font-medium transition-colors"
                :class="bankLanguage === language ? 'bg-moss text-moss-fg' : 'bg-transparent text-ink-2 hover:bg-paper-2'"
                @click="setBankLanguage(language)"
              >
                {{ LANG_BADGE[language] }}
              </button>
            </div>
          </div>

          <!-- Only the very first open of a subject shows the plain loading
               text (nothing to keep on screen yet). A page change keeps the
               existing list mounted -- dimmed, not removed -- so the
               document height never collapses and the scroll position never
               gets reclamped to a shorter page. -->
          <div v-if="questionsLoading && !questionsBySubject[selectedSubject.id]" class="space-y-2">
            <div v-for="n in 4" :key="n" class="h-20 animate-pulse rounded-xl bg-paper-2" />
          </div>
          <template v-else>
            <div :class="{ 'pointer-events-none opacity-50 transition-opacity duration-150': questionsLoading }">
              <!-- ── Search + compact match counter ─────────────────────── -->
              <div v-if="questionsBySubject[selectedSubject.id]?.length" class="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
                <div class="relative min-w-0 flex-1">
                  <Search :size="15" :stroke-width="1.8" class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
                  <input
                    v-model="searchQuery"
                    type="text"
                    placeholder="Поиск по тексту вопроса..."
                    class="input pl-9"
                  />
                </div>
                <span class="shrink-0 whitespace-nowrap rounded-lg bg-paper-2 px-2.5 py-1 text-xs font-medium text-ink-2">
                  Найдено: {{ filteredQuestions.length }}
                </span>
              </div>

              <div
                v-if="filteredQuestions.length"
                class="mb-3 flex flex-wrap items-center gap-2 text-sm text-ink-2"
              >
                <input
                  type="checkbox"
                  class="h-4 w-4 accent-moss"
                  :checked="allVisibleSelected()"
                  aria-label="Выбрать все вопросы на экране"
                  @click.stop="toggleSelectAllVisible()"
                />
                <span>Выбрать все на этом экране ({{ filteredQuestions.length }})</span>
                <span
                  v-if="questionsPageFor(selectedSubject.id).total > questionsBySubject[selectedSubject.id].length"
                  class="text-ink-3"
                >
                  из {{ questionsPageFor(selectedSubject.id).total }} по текущему фильтру
                </span>
              </div>

              <!-- ── Sticky bulk-action bar: only takes space once something is selected ── -->
              <div
                v-if="selectedIds.size > 0"
                class="sticky top-2 z-10 mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-moss/30 bg-moss/10 px-3 py-2 text-sm"
              >
                <span class="font-medium text-ink">Выбрано: {{ selectedIds.size }}</span>
                <div class="flex items-center gap-3">
                  <button type="button" class="text-ink-2 hover:text-ink" @click="clearSelection()">
                    Снять выбор
                  </button>
                  <BaseButton variant="danger" class="!px-3 !py-1.5 !text-xs" :disabled="selectedIds.size === 0" @click="openBulkDeleteModal">
                    <Trash2 :size="14" :stroke-width="1.8" />
                    Удалить выбранные ({{ selectedIds.size }})
                  </BaseButton>
                </div>
              </div>

              <ul class="space-y-2">
                <li
                  v-for="(q, index) in filteredQuestions"
                  :key="q.id"
                  class="card p-5 transition-all"
                  :class="questionCardClass(q)"
                >
                  <!-- ── In-place edit: the card itself becomes the form, so
                       saving/cancelling never moves the scroll position. ── -->
                  <EntQuestionForm
                    v-if="editingQuestionId === q.id && editForm"
                    :form="editForm"
                    mode="edit"
                    :image-url="q.has_image ? questionImageUrl(q.id) : null"
                    :file-input-key="editFileInputKey"
                    @save="handleUpdateQuestion(selectedSubject.id)"
                    @cancel="cancelEditQuestion"
                    @image-picked="onEditImagePicked"
                    @remove-image="handleRemoveEditImage(selectedSubject.id)"
                  />
                  <div v-else class="flex items-start justify-between gap-3">
                    <div class="flex min-w-0 gap-3">
                      <input
                        type="checkbox"
                        class="mt-1 h-4 w-4 shrink-0 accent-moss"
                        :checked="selectedIds.has(q.id)"
                        :aria-label="`Выбрать вопрос: ${q.text}`"
                        @click.stop="toggleQuestionSelection(index, $event)"
                      />
                      <img
                        v-if="q.has_image"
                        :src="questionImageUrl(q.id)"
                        alt=""
                        class="h-16 w-24 shrink-0 rounded-lg border border-line object-cover"
                      />
                      <div class="min-w-0">
                        <div class="mb-1.5 flex flex-wrap items-center gap-1.5">
                          <BaseBadge tone="neutral">{{ LANG_BADGE[q.language] }}</BaseBadge>
                          <BaseBadge tone="neutral">{{ QTYPE_BADGE[q.qtype] }}</BaseBadge>
                          <BaseBadge tone="neutral">{{ q.max_score }} балл{{ q.max_score > 1 ? "а" : "" }}</BaseBadge>
                          <BaseBadge v-if="questionNeedsReview(q)" tone="warning">Нет ответа</BaseBadge>
                        </div>
                        <p class="text-sm text-ink-2">{{ q.text }}</p>
                      </div>
                    </div>
                    <div class="flex shrink-0 gap-1">
                      <button
                        type="button"
                        class="flex h-11 w-11 items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-paper-2 hover:text-ink"
                        aria-label="Редактировать вопрос"
                        title="Редактировать"
                        @click="startEditQuestion(q)"
                      >
                        <Pencil :size="16" :stroke-width="1.8" />
                      </button>
                      <button
                        type="button"
                        class="flex h-11 w-11 items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-clay/10 hover:text-clay"
                        aria-label="Удалить вопрос"
                        title="Удалить вопрос"
                        @click="handleDeleteQuestion(selectedSubject.id, q.id)"
                      >
                        <Trash2 :size="16" :stroke-width="1.8" />
                      </button>
                    </div>
                  </div>
                </li>
                <li v-if="!questionsBySubject[selectedSubject.id]?.length" class="list-none">
                  <div class="card flex flex-col items-center gap-2 px-6 py-10 text-center">
                    <span class="text-2xl">📭</span>
                    <p class="text-ink-2">
                      {{
                        bankLanguage === "all"
                          ? "Вопросов пока нет."
                          : `Вопросов на языке «${LANGUAGE_LABEL[bankLanguage]}» пока нет.`
                      }}
                    </p>
                  </div>
                </li>
                <li
                  v-else-if="!filteredQuestions.length"
                  class="text-sm text-ink-2"
                >
                  Совпадений по запросу «{{ searchQuery }}» не найдено.
                </li>
              </ul>
            </div>

            <PaginationControls
              :page="questionsPageFor(selectedSubject.id).page"
              :pages="questionsPageFor(selectedSubject.id).pages"
              :total="questionsPageFor(selectedSubject.id).total"
              @change="changeQuestionsPage(selectedSubject.id, $event)"
            />
          </template>

          <div class="card p-5">
            <EntQuestionForm
              :form="questionForms[selectedSubject.id]"
              mode="create"
              :file-input-key="fileInputKey"
              @save="handleCreateQuestion(selectedSubject.id)"
              @image-picked="onNewImagePicked(selectedSubject.id, $event)"
              @remove-image="handleRemoveNewImage(selectedSubject.id)"
            />
          </div>
        </template>
      </section>
    </div>

    <!-- ── Subject structure (qtype quota) modal ─────────────────────── -->
    <div
      v-if="quotaModalSubject"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      @click.self="closeQuotaModal"
    >
      <div ref="quotaModalRef" role="dialog" aria-modal="true" class="card max-h-[90dvh] w-full max-w-md overflow-y-auto p-5">
        <h2 class="mb-1 text-lg font-semibold text-ink">Структура предмета «{{ quotaModalSubject.name }}»</h2>
        <p class="mb-4 text-sm text-ink-2">
          Сколько вопросов каждого типа брать при генерации симуляции. Если всё оставить по 0, предмет останется в
          старом режиме — случайная выборка без учёта типа.
        </p>

        <div class="space-y-3">
          <label class="block text-sm">
            <span class="mb-1.5 block font-medium text-ink-2">Один правильный ответ (single choice)</span>
            <input v-model.number="quotaForm.single_choice_count" type="number" min="0" max="100" class="input min-h-11" />
          </label>
          <label class="block text-sm">
            <span class="mb-1.5 block font-medium text-ink-2">Несколько правильных ответов (multiple choice)</span>
            <input v-model.number="quotaForm.multiple_choice_count" type="number" min="0" max="100" class="input min-h-11" />
          </label>
          <label class="block text-sm">
            <span class="mb-1.5 block font-medium text-ink-2">Сопоставление (matching)</span>
            <input v-model.number="quotaForm.matching_count" type="number" min="0" max="100" class="input min-h-11" />
          </label>
          <label class="block text-sm">
            <span class="mb-1.5 block font-medium text-ink-2">Краткий ответ (short answer)</span>
            <input v-model.number="quotaForm.short_answer_count" type="number" min="0" max="100" class="input min-h-11" />
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
    <div v-if="bulkDeleteModalOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        ref="bulkDeleteModalRef"
        role="dialog"
        aria-modal="true"
        class="card max-h-[90dvh] w-full max-w-md overflow-y-auto p-5"
      >
        <h2 class="mb-1 text-lg font-semibold text-ink">Удалить выбранные вопросы?</h2>
        <p class="mb-4 text-sm text-ink-2">
          Будет удалено вопросов: <strong>{{ selectedIds.size }}</strong
          >. Это действие нельзя отменить.
        </p>

        <label v-if="needsTypedConfirm" class="mb-4 block text-sm">
          <span class="mb-1.5 block font-medium text-ink-2">
            Введите количество удаляемых вопросов ({{ selectedIds.size }}) для подтверждения
          </span>
          <input
            v-model="bulkDeleteConfirmText"
            type="text"
            inputmode="numeric"
            class="input min-h-11"
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
      class="fixed bottom-[max(1rem,env(safe-area-inset-bottom))] left-1/2 z-50 -translate-x-1/2 rounded-lg px-4 py-2.5 text-sm shadow-lg"
      :class="toast.tone === 'error' ? 'bg-clay text-white' : 'bg-moss text-moss-fg'"
      role="status"
    >
      {{ toast.message }}
    </div>
  </PageContainer>
</template>
