<script setup lang="ts">
import {
  ChevronDown,
  CircleCheck,
  FileText,
  FolderOpen,
  ClipboardCheck,
  ListChecks,
  Pencil,
  Plus,
  Presentation,
  Trash2,
  Video,
} from "@lucide/vue";
import { isAxiosError } from "axios";
import { defineAsyncComponent, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";

import {
  deleteCategoryImage,
  getCategoryImageUrl,
  getTeacherCategory,
  updateTeacherCategory,
  uploadCategoryImage,
} from "@/api/categories";
import { createLesson, deleteLesson, updateLesson } from "@/api/lessons";
import { createSection, deleteSection, listTeacherSections, updateSection } from "@/api/sections";
import {
  MAX_PRESENTATION_BYTES,
  PRESENTATION_ACCEPT,
  PRESENTATION_EXTENSIONS,
  deleteLessonPresentation,
  formatFileSize,
  getTeacherPresentationLink,
  uploadLessonPresentation,
} from "@/api/presentation";
import { deleteLessonVideo, getTeacherLesson, uploadLessonVideo } from "@/api/video";
import PresentationViewer from "@/components/media/PresentationViewer.vue";
import HwBuilder from "@/components/autohw/HwBuilder.vue";
import QuestionBank from "@/components/course/QuestionBank.vue";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import BaseInput from "@/components/ui/BaseInput.vue";
import type { Category, LessonSummary, Section, VideoStatus } from "@/types";
import { describeApiError } from "@/utils/apiError";
import { pluralRu } from "@/utils/subjectTheme";

// TipTap is most of this page's bundle and only a lesson form uses it, so the
// section list renders before the editor has downloaded.
const RichTextEditor = defineAsyncComponent(() => import("@/components/richtext/RichTextEditor.vue"));

const route = useRoute();
const categoryId = Number(route.params.id);

const category = ref<Category | null>(null);
const categoryDescEditing = ref(false);
const categoryDescDraft = ref("");
const categoryImageUploading = ref(false);
const categoryImageError = ref("");
const categoryImageCacheBust = ref(0);

const sections = ref<Section[]>([]);
const loading = ref(true);
const pageError = ref(false);

const newSectionTitle = ref("");
const newSectionDescription = ref("");

const lessonForms = reactive<
  Record<number, { title: string; description: string; homework: string; video: string; open: boolean }>
>({});
const videoUploadState = reactive<Record<number, { uploading: boolean; progress: number; error: string }>>({});
const pollTimers: Record<number, ReturnType<typeof setTimeout>> = {};
const presentationState = reactive<
  Record<number, { uploading: boolean; progress: number; error: string; preview: boolean }>
>({});

function presentationUi(lessonId: number) {
  return (presentationState[lessonId] ??= { uploading: false, progress: 0, error: "", preview: false });
}

const sectionEditForms = reactive<Record<number, { title: string; description: string; open: boolean }>>({});
const lessonEditForms = reactive<
  Record<number, { title: string; description: string; homework: string; video: string; open: boolean; loading: boolean }>
>({});

const videoStatusTone: Record<VideoStatus, "neutral" | "success" | "warning" | "danger"> = {
  none: "neutral",
  processing: "warning",
  ready: "success",
  failed: "danger",
};
const videoStatusLabel: Record<VideoStatus, string> = {
  none: "Видео не загружено",
  processing: "Обрабатывается…",
  ready: "Видео готово",
  failed: "Ошибка обработки",
};

// Lessons start collapsed. Previously every lesson rendered its video
// controls and its whole question bank inline, so an 11-lesson course was a
// wall of forms with no way to see the course as a whole.
const openLessonIds = ref<Set<number>>(new Set());
const openSectionTestIds = ref<Set<number>>(new Set());

function toggleIn(set: Set<number>, id: number) {
  if (set.has(id)) set.delete(id);
  else set.add(id);
  // Reassign so the Set change is picked up by reactivity.
  return new Set(set);
}

function toggleLesson(id: number) {
  openLessonIds.value = toggleIn(openLessonIds.value, id);
}
function toggleSectionTest(id: number) {
  openSectionTestIds.value = toggleIn(openSectionTestIds.value, id);
}

/** What a teacher needs to know about a lesson without opening it. */
function lessonChips(lesson: LessonSummary) {
  return [
    {
      key: "video",
      icon: Video,
      label:
        lesson.video_status === "ready"
          ? "Видео"
          : lesson.video_url && lesson.video_status === "none"
            ? "YouTube"
            : videoStatusLabel[lesson.video_status],
      done: lesson.video_status === "ready" || (!!lesson.video_url && lesson.video_status === "none"),
      pending: lesson.video_status === "processing",
      failed: lesson.video_status === "failed",
    },
    {
      key: "questions",
      icon: ListChecks,
      label: lesson.question_count ? `${lesson.question_count} вопр.` : "Нет вопросов",
      done: lesson.question_count > 0,
    },
    {
      key: "homework",
      icon: FileText,
      label: lesson.auto_hw_tasks
        ? `Домашка: ${lesson.auto_hw_tasks} ${pluralRu(lesson.auto_hw_tasks, ["задание", "задания", "заданий"])}`
        : lesson.has_homework
          ? "Домашка"
          : "Без домашки",
      done: lesson.has_homework,
    },
    // Optional material: shown only when there is one, never as "missing".
    ...(lesson.presentation_name
      ? [{ key: "presentation", icon: Presentation, label: "Презентация", done: true }]
      : []),
  ];
}

// The open lesson is edited step by step: one block on screen at a time
// instead of a long wall of forms. Blocks stay mounted (v-show), so moving
// between steps never drops a half-typed question or task.
type LessonStep = "video" | "presentation" | "test" | "homework";
const LESSON_STEPS: { key: LessonStep; label: string }[] = [
  { key: "video", label: "Видео" },
  { key: "presentation", label: "Презентация" },
  { key: "test", label: "Мини-тест" },
  { key: "homework", label: "Домашка" },
];
const lessonStep = reactive<Record<number, LessonStep>>({});

function stepOf(lessonId: number): LessonStep {
  return lessonStep[lessonId] ?? "video";
}
function stepIndex(lessonId: number): number {
  return LESSON_STEPS.findIndex((s) => s.key === stepOf(lessonId));
}
function goStep(lessonId: number, delta: number) {
  const next = LESSON_STEPS[stepIndex(lessonId) + delta];
  if (next) lessonStep[lessonId] = next.key;
  requestAnimationFrame(() =>
    document.getElementById(`lesson-steps-${lessonId}`)?.scrollIntoView({ behavior: "smooth", block: "start" }),
  );
}
function stepDone(lesson: LessonSummary, key: LessonStep): boolean | null {
  if (key === "video") return lesson.video_status === "ready" || (!!lesson.video_url && lesson.video_status === "none");
  if (key === "presentation") return lesson.presentation_name ? true : null; // optional: never "missing"
  if (key === "test") return lesson.question_count > 0;
  return lesson.has_homework;
}

function lessonIsReady(lesson: LessonSummary): boolean {
  return lesson.video_status === "ready" && lesson.question_count > 0;
}

async function load() {
  loading.value = true;
  sections.value = await listTeacherSections(categoryId);
  loading.value = false;
}

/** Re-reads the lesson chips (video, test, homework) without the loading
 *  state, so an open lesson and its half-filled forms stay on screen. */
async function refreshLessonSummaries() {
  try {
    const fresh = await listTeacherSections(categoryId);
    const byId = new Map(fresh.flatMap((sec) => sec.lessons).map((l) => [l.id, l]));
    for (const sec of sections.value) {
      for (const lesson of sec.lessons) {
        const f = byId.get(lesson.id);
        if (f) Object.assign(lesson, f);
      }
    }
  } catch {
    /* the chips just keep their previous state */
  }
}

async function initialLoad() {
  pageError.value = false;
  loading.value = true;
  try {
    category.value = await getTeacherCategory(categoryId);
    await load();
  } catch {
    pageError.value = true;
    loading.value = false;
  }
}

onMounted(initialLoad);

function startEditCategoryDescription() {
  categoryDescDraft.value = category.value?.description ?? "";
  categoryDescEditing.value = true;
}

async function saveCategoryDescription() {
  category.value = await updateTeacherCategory(categoryId, { description: categoryDescDraft.value });
  categoryDescEditing.value = false;
}

function handleCategoryImageChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (file) uploadCategoryImageFile(file);
}

async function uploadCategoryImageFile(file: File) {
  categoryImageUploading.value = true;
  categoryImageError.value = "";
  try {
    category.value = await uploadCategoryImage(categoryId, file);
    categoryImageCacheBust.value++;
  } catch {
    categoryImageError.value = "Не удалось загрузить изображение";
  } finally {
    categoryImageUploading.value = false;
  }
}

async function handleDeleteCategoryImage() {
  category.value = await deleteCategoryImage(categoryId);
  categoryImageCacheBust.value++;
}

function startEditSection(section: Section) {
  sectionEditForms[section.id] = { title: section.title, description: section.description ?? "", open: true };
}

function cancelEditSection(sectionId: number) {
  sectionEditForms[sectionId].open = false;
}

// One banner for every structural action below. None of them caught a
// failure before: a refused save or a server error left the form exactly
// as it was, and the teacher had no way to tell nothing had happened.
const actionError = ref("");

async function guarded(failure: string, action: () => Promise<void>): Promise<boolean> {
  actionError.value = "";
  try {
    await action();
    return true;
  } catch (e) {
    const detail = isAxiosError(e) ? e.response?.data?.detail : null;
    actionError.value =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail) && detail[0]?.msg
          ? `${failure}: ${String(detail[0].msg).replace(/^Value error, /, "")}`
          : failure;
    return false;
  }
}

async function saveSection(sectionId: number) {
  const form = sectionEditForms[sectionId];
  if (!form.title.trim()) return;
  const ok = await guarded("Не удалось сохранить раздел", () =>
    updateSection(sectionId, { title: form.title, description: form.description || undefined }).then(() => undefined),
  );
  if (!ok) return;
  form.open = false;
  await load();
}

async function handleDeleteSection(sectionId: number) {
  if (!confirm("Удалить раздел и все его уроки? Это действие необратимо.")) return;
  if (await guarded("Не удалось удалить раздел", () => deleteSection(sectionId).then(() => undefined))) await load();
}

async function startEditLesson(lessonId: number) {
  lessonEditForms[lessonId] = { title: "", description: "", homework: "", video: "", open: true, loading: true };
  const full = await getTeacherLesson(lessonId);
  lessonEditForms[lessonId] = {
    title: full.title,
    description: full.description ?? "",
    homework: full.homework_assignment ?? "",
    video: full.video_url ?? "",
    open: true,
    loading: false,
  };
}

function cancelEditLesson(lessonId: number) {
  lessonEditForms[lessonId].open = false;
}

async function saveLesson(lessonId: number) {
  const form = lessonEditForms[lessonId];
  if (!form.title.trim()) return;
  const ok = await guarded("Не удалось сохранить урок", () =>
    updateLesson(lessonId, {
      title: form.title,
      description: form.description || undefined,
      homework_assignment: form.homework || undefined,
      // Always sent: "" is how the teacher removes a YouTube link.
      video_url: form.video.trim(),
    }),
  );
  if (!ok) return;
  form.open = false;
  await load();
}

async function handleDeleteLesson(lessonId: number) {
  if (!confirm("Удалить урок вместе с видео, вопросами и домашкой? Это действие необратимо.")) return;
  if (await guarded("Не удалось удалить урок", () => deleteLesson(lessonId).then(() => undefined))) await load();
}
onBeforeUnmount(() => {
  for (const timer of Object.values(pollTimers)) clearTimeout(timer);
});

function setLessonVideoStatus(lessonId: number, status: VideoStatus) {
  for (const section of sections.value) {
    const lesson = section.lessons.find((l) => l.id === lessonId);
    if (lesson) lesson.video_status = status;
  }
}

function pollVideoStatus(lessonId: number) {
  pollTimers[lessonId] = setTimeout(async () => {
    try {
      const updated = await getTeacherLesson(lessonId);
      setLessonVideoStatus(lessonId, updated.video_status);
      if (updated.video_status === "processing") pollVideoStatus(lessonId);
    } catch {
      // Stop polling silently; the teacher can just re-open the page.
    }
  }, 4000);
}

function handleVideoFileChange(lessonId: number, event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (file) uploadVideo(lessonId, file);
}

async function uploadVideo(lessonId: number, file: File) {
  videoUploadState[lessonId] = { uploading: true, progress: 0, error: "" };
  try {
    const updated = await uploadLessonVideo(lessonId, file, (percent) => {
      videoUploadState[lessonId].progress = percent;
    });
    setLessonVideoStatus(lessonId, updated.video_status);
    pollVideoStatus(lessonId);
  } catch {
    videoUploadState[lessonId].error = "Не удалось загрузить видео";
  } finally {
    videoUploadState[lessonId].uploading = false;
  }
}

function setLessonPresentation(lessonId: number, name: string | null, size: number | null) {
  for (const section of sections.value) {
    const lesson = section.lessons.find((l) => l.id === lessonId);
    if (lesson) {
      lesson.presentation_name = name;
      lesson.presentation_size = size;
    }
  }
}

function handlePresentationFileChange(lessonId: number, event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (file) uploadPresentation(lessonId, file);
}

async function uploadPresentation(lessonId: number, file: File) {
  const ui = presentationUi(lessonId);
  ui.error = "";
  const lower = file.name.toLowerCase();
  if (!PRESENTATION_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
    ui.error =
      "Подходят .pptx, .ppsx или PDF. Старый .ppt или Google Slides сохраните как .pptx (Файл → Сохранить как / Скачать).";
    return;
  }
  if (file.size > MAX_PRESENTATION_BYTES) {
    ui.error = "Файл больше 10 МБ. Сожмите картинки (в PowerPoint: Файл → Сжать рисунки) или уменьшите PDF.";
    return;
  }
  ui.uploading = true;
  ui.progress = 0;
  ui.preview = false;
  try {
    const updated = await uploadLessonPresentation(lessonId, file, (percent) => (ui.progress = percent));
    setLessonPresentation(lessonId, updated.presentation_name, updated.presentation_size);
  } catch (e) {
    ui.error = describeApiError(e, "Не удалось загрузить презентацию");
  } finally {
    ui.uploading = false;
  }
}

async function handleDeletePresentation(lessonId: number) {
  if (!confirm("Удалить презентацию из урока?")) return;
  const ui = presentationUi(lessonId);
  try {
    await deleteLessonPresentation(lessonId);
    ui.preview = false;
    setLessonPresentation(lessonId, null, null);
  } catch (e) {
    ui.error = describeApiError(e, "Не удалось удалить презентацию");
  }
}

async function handleDeleteVideo(lessonId: number) {
  await deleteLessonVideo(lessonId);
  setLessonVideoStatus(lessonId, "none");
}

async function handleCreateSection() {
  if (!newSectionTitle.value.trim()) return;
  const ok = await guarded("Не удалось создать раздел", () =>
    createSection(categoryId, {
      title: newSectionTitle.value,
      description: newSectionDescription.value || undefined,
    }).then(() => undefined),
  );
  if (!ok) return;
  newSectionTitle.value = "";
  newSectionDescription.value = "";
  await load();
}

function openLessonForm(sectionId: number) {
  lessonForms[sectionId] = { title: "", description: "", homework: "", video: "", open: true };
}

async function handleCreateLesson(sectionId: number) {
  const form = lessonForms[sectionId];
  if (!form?.title.trim()) return;
  const ok = await guarded("Не удалось создать урок", () =>
    createLesson(sectionId, {
      title: form.title,
      description: form.description || undefined,
      homework_assignment: form.homework || undefined,
      video_url: form.video.trim() || undefined,
    }),
  );
  if (!ok) return;
  lessonForms[sectionId] = { title: "", description: "", homework: "", video: "", open: false };
  await load();
}

</script>

<template>
  <PageContainer>
    <PageHeader title="Конструктор курса" :subtitle="category ? category.name : undefined" />

    <div v-if="loading" class="space-y-6">
      <div class="h-32 animate-pulse rounded-xl bg-paper-2" />
      <div class="h-24 animate-pulse rounded-xl bg-paper-2" />
      <div class="h-40 animate-pulse rounded-xl bg-paper-2" />
    </div>

    <div v-else-if="pageError" class="card py-12 text-center">
      <p class="text-ink-2">Не удалось загрузить курс.</p>
      <BaseButton class="mt-4" @click="initialLoad">Повторить</BaseButton>
    </div>

    <template v-else>
      <div
        v-if="actionError"
        class="sticky z-20 mb-4 flex items-start gap-3 rounded-xl border border-red-500/30 bg-red-50 p-3 text-sm text-red-700 shadow-sm dark:bg-red-950/60 dark:text-red-300"
        :style="{ top: 'calc(env(safe-area-inset-top, 0px) + 0.75rem)' }"
        role="alert"
      >
        <span class="flex-1">{{ actionError }}</span>
        <button type="button" class="shrink-0 underline underline-offset-2" @click="actionError = ''">Закрыть</button>
      </div>
      <div v-if="category" class="card mb-6 flex flex-col gap-4 p-4 sm:flex-row">
        <img
          v-if="category.has_image"
          :src="`${getCategoryImageUrl(categoryId)}?v=${categoryImageCacheBust}`"
          alt=""
          class="h-28 w-28 shrink-0 rounded-lg object-cover"
        />
        <div class="flex-1">
          <h2 class="font-display text-display-sm text-ink">{{ category.name }}</h2>
          <div v-if="!categoryDescEditing">
            <p class="mt-1 text-sm text-ink-2">{{ category.description || "Описание не задано" }}</p>
            <button class="mt-2 text-sm text-moss underline" @click="startEditCategoryDescription">
              Редактировать описание
            </button>
          </div>
          <div v-else class="mt-2 space-y-2">
            <textarea v-model="categoryDescDraft" rows="3" class="input" />
            <div class="flex gap-2">
              <BaseButton @click="saveCategoryDescription">Сохранить</BaseButton>
              <BaseButton variant="secondary" @click="categoryDescEditing = false">Отмена</BaseButton>
            </div>
          </div>

          <div class="mt-3 flex flex-wrap items-center gap-2">
            <label class="cursor-pointer text-sm text-moss underline">
              {{ category.has_image ? "Заменить картинку" : "Загрузить картинку" }}
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                class="hidden"
                :disabled="categoryImageUploading"
                @change="handleCategoryImageChange"
              />
            </label>
            <BaseButton v-if="category.has_image" variant="secondary" @click="handleDeleteCategoryImage">
              Удалить картинку
            </BaseButton>
            <span v-if="categoryImageUploading" class="text-sm text-ink-2">Загрузка…</span>
            <span v-if="categoryImageError" class="text-sm text-clay">{{ categoryImageError }}</span>
          </div>
        </div>
      </div>

      <div v-if="!sections.length" class="card py-12 text-center">
        <FolderOpen :size="30" :stroke-width="1.6" class="text-ink-3" />
        <p class="mt-3 text-ink-2">В этой категории пока нет разделов — добавьте первый раздел ниже.</p>
      </div>

      <div class="space-y-6">
        <form class="card flex flex-col gap-3 p-4 sm:flex-row sm:items-end" @submit.prevent="handleCreateSection">
          <BaseInput v-model="newSectionTitle" label="Новый раздел" :maxlength="200" class="flex-1" />
          <BaseInput v-model="newSectionDescription" label="Описание" class="flex-1" />
          <BaseButton type="submit">Добавить</BaseButton>
        </form>

        <div v-for="(section, sectionIndex) in sections" :key="section.id" class="card overflow-hidden">
          <!-- ── Заголовок раздела ─────────────────────────────────── -->
          <div
            v-if="!sectionEditForms[section.id]?.open"
            class="flex flex-col gap-3 border-b border-line bg-paper-2/50 p-4 sm:flex-row sm:items-start sm:justify-between"
          >
            <div class="flex min-w-0 gap-3">
              <span
                class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-moss/10 text-sm font-bold text-moss"
              >
                {{ sectionIndex + 1 }}
              </span>
              <div class="min-w-0">
                <h2 class="text-lg font-semibold text-ink">{{ section.title }}</h2>
                <p v-if="section.description" class="mt-0.5 text-sm text-ink-2">{{ section.description }}</p>
                <p class="mt-1 text-xs text-ink-3">
                  {{ section.lessons.length }}
                  {{ pluralRu(section.lessons.length, ["урок", "урока", "уроков"]) }}
                </p>
              </div>
            </div>
            <!-- Каждая кнопка называет свой объект: на странице три уровня
                 редактирования, и одинаковое «Редактировать» не давало понять,
                 что именно откроется. -->
            <div class="flex shrink-0 flex-wrap gap-2">
              <button
                class="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-line bg-paper px-3 text-sm font-medium text-ink-2 transition-all duration-200 hover:border-moss/50 hover:text-ink"
                @click="startEditSection(section)"
              >
                <Pencil :size="14" :stroke-width="1.8" />
                Название раздела
              </button>
              <button
                class="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-line bg-paper px-3 text-sm font-medium text-clay transition-all duration-200 hover:border-clay/40"
                @click="handleDeleteSection(section.id)"
              >
                <Trash2 :size="14" :stroke-width="1.8" />
                Удалить раздел
              </button>
            </div>
          </div>

          <div v-else class="space-y-3 border-b border-line bg-paper-2 p-4">
            <p class="text-sm font-medium text-ink">Редактирование раздела</p>
            <BaseInput v-model="sectionEditForms[section.id].title" label="Название раздела" :maxlength="200" />
            <BaseInput v-model="sectionEditForms[section.id].description" label="Описание раздела" />
            <div class="flex gap-2">
              <BaseButton @click="saveSection(section.id)">Сохранить раздел</BaseButton>
              <BaseButton variant="secondary" @click="cancelEditSection(section.id)">Отмена</BaseButton>
            </div>
          </div>

          <div class="p-4">

          <p v-if="!section.lessons.length" class="mb-3 rounded-lg border border-dashed border-line-strong p-6 text-center text-sm text-ink-3">
            В разделе пока нет уроков
          </p>

          <ul v-else class="mb-3 space-y-2">
            <li v-for="(lesson, lessonIndex) in section.lessons" :key="lesson.id" class="overflow-hidden rounded-xl border border-line">
              <!-- Свёрнутая строка: всё состояние урока видно сразу, без
                   раскрытия — есть ли видео, вопросы и домашнее задание. -->
              <button
                v-if="!lessonEditForms[lesson.id]?.open"
                type="button"
                class="flex w-full items-center gap-3 p-3 text-left transition-colors duration-200 hover:bg-paper-2"
                :aria-expanded="openLessonIds.has(lesson.id)"
                @click="toggleLesson(lesson.id)"
              >
                <span
                  class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs font-semibold"
                  :class="lessonIsReady(lesson) ? 'bg-moss/15 text-moss' : 'bg-paper-2 text-ink-3'"
                >
                  {{ lessonIndex + 1 }}
                </span>

                <span class="min-w-0 flex-1">
                  <span class="line-clamp-2 font-medium leading-snug text-ink">{{ lesson.title }}</span>
                  <span class="mt-1 flex flex-wrap gap-1.5">
                    <span
                      v-for="chip in lessonChips(lesson)"
                      :key="chip.key"
                      class="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium"
                      :class="
                        chip.failed
                          ? 'bg-red-500/10 text-red-600 dark:text-red-400'
                          : chip.pending
                            ? 'bg-amber-500/10 text-amber-700 dark:text-amber-500'
                            : chip.done
                              ? 'bg-moss/10 text-moss'
                              : 'bg-paper-2 text-ink-3'
                      "
                    >
                      <component :is="chip.icon" :size="11" :stroke-width="2" />
                      {{ chip.label }}
                    </span>
                  </span>
                </span>

                <CircleCheck
                  v-if="lessonIsReady(lesson)"
                  :size="16"
                  :stroke-width="2"
                  class="shrink-0 text-moss"
                  aria-label="Урок готов"
                />
                <ChevronDown
                  :size="17"
                  :stroke-width="2"
                  class="shrink-0 text-ink-3 transition-transform duration-200"
                  :class="openLessonIds.has(lesson.id) ? 'rotate-180' : ''"
                />
              </button>
              <!-- Форма редактирования материалов урока -->
              <div v-else class="space-y-3 border-t border-line bg-paper-2 p-4">
                <p class="text-sm font-medium text-ink">Материалы урока</p>
                <p v-if="lessonEditForms[lesson.id].loading" class="text-sm text-ink-2">Загрузка…</p>
                <template v-else>
                  <BaseInput v-model="lessonEditForms[lesson.id].title" label="Название урока" :maxlength="200" />
                  <BaseInput
                    v-model="lessonEditForms[lesson.id].video"
                    label="Видео с YouTube (необязательно)"
                    placeholder="https://www.youtube.com/watch?v=…"
                    :maxlength="500"
                  />
                  <RichTextEditor v-model="lessonEditForms[lesson.id].description" label="Описание и теория (видит ученик под видео)" />
                  <RichTextEditor
                    v-model="lessonEditForms[lesson.id].homework"
                    label="Домашнее задание"
                    min-height="8rem"
                  />
                  <div class="flex gap-2">
                    <BaseButton @click="saveLesson(lesson.id)">Сохранить урок</BaseButton>
                    <BaseButton variant="secondary" @click="cancelEditLesson(lesson.id)">Отмена</BaseButton>
                  </div>
                </template>
              </div>

              <!-- Раскрытая карточка урока: три чётко названных блока вместо
                   сплошной ленты форм. -->
              <div v-if="openLessonIds.has(lesson.id) && !lessonEditForms[lesson.id]?.open" class="border-t border-line">
                <div class="flex flex-wrap gap-2 border-b border-line bg-paper-2/40 p-3">
                  <button
                    class="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-line bg-paper px-3 text-sm font-medium text-ink-2 transition-all duration-200 hover:border-moss/50 hover:text-ink"
                    @click="startEditLesson(lesson.id)"
                  >
                    <Pencil :size="14" :stroke-width="1.8" />
                    Название, теория, домашка
                  </button>
                  <button
                    class="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-line bg-paper px-3 text-sm font-medium text-clay transition-all duration-200 hover:border-clay/40"
                    @click="handleDeleteLesson(lesson.id)"
                  >
                    <Trash2 :size="14" :stroke-width="1.8" />
                    Удалить урок
                  </button>
                </div>

                <nav
                  :id="`lesson-steps-${lesson.id}`"
                  class="grid scroll-mt-32 grid-cols-2 gap-2 border-b border-line p-3 sm:grid-cols-4"
                  aria-label="Шаги урока"
                >
                  <button
                    v-for="(st, si) in LESSON_STEPS"
                    :key="st.key"
                    type="button"
                    class="flex min-h-12 min-w-0 items-center gap-2 rounded-xl border-2 px-2 text-left text-sm font-semibold transition-colors sm:px-3 sm:text-base"
                    :class="stepOf(lesson.id) === st.key ? 'border-moss bg-moss/10 text-moss' : 'border-line text-ink-2 hover:border-moss/40'"
                    :aria-current="stepOf(lesson.id) === st.key ? 'step' : undefined"
                    @click="lessonStep[lesson.id] = st.key"
                  >
                    <span
                      class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold sm:h-7 sm:w-7 sm:text-sm"
                      :class="stepDone(lesson, st.key) ? 'bg-moss text-white' : 'bg-paper-2 text-ink-3'"
                    >
                      {{ stepDone(lesson, st.key) ? "✓" : si + 1 }}
                    </span>
                    <span class="min-w-0">
                      {{ st.label }}
                      <span v-if="st.key === 'presentation'" class="hidden text-xs font-normal text-ink-3 sm:block">по желанию</span>
                    </span>
                  </button>
                </nav>

                <div class="space-y-4 p-3">
                  <section v-show="stepOf(lesson.id) === 'video'">
                    <p class="mb-2 flex items-center gap-1.5 text-sm font-medium text-ink">
                      <Video :size="15" :stroke-width="1.8" class="text-ink-3" />
                      Видеоурок
                    </p>
                    <div class="flex flex-wrap items-center gap-2">
                      <BaseBadge v-if="lesson.video_url && lesson.video_status === 'none'" tone="success">
                        YouTube
                      </BaseBadge>
                      <BaseBadge v-else :tone="videoStatusTone[lesson.video_status]">
                        {{ videoStatusLabel[lesson.video_status] }}
                      </BaseBadge>
                      <label
                        class="inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-lg border border-line bg-paper px-3 text-sm font-medium text-ink-2 transition-all duration-200 hover:border-moss/50 hover:text-ink"
                      >
                        <Plus :size="14" :stroke-width="2" />
                        {{ lesson.video_status === "none" ? "Загрузить видео" : "Заменить видео" }}
                        <input
                          type="file"
                          accept="video/*"
                          class="hidden"
                          :disabled="videoUploadState[lesson.id]?.uploading"
                          @change="handleVideoFileChange(lesson.id, $event)"
                        />
                      </label>
                      <button
                        v-if="lesson.video_status !== 'none'"
                        class="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-line bg-paper px-3 text-sm font-medium text-clay transition-all duration-200 hover:border-clay/40 disabled:opacity-50"
                        :disabled="videoUploadState[lesson.id]?.uploading"
                        @click="handleDeleteVideo(lesson.id)"
                      >
                        <Trash2 :size="14" :stroke-width="1.8" />
                        Удалить видео
                      </button>
                    </div>
                    <div v-if="videoUploadState[lesson.id]?.uploading" class="mt-2">
                      <div class="h-1.5 overflow-hidden rounded-full bg-paper-2">
                        <div
                          class="h-full rounded-full bg-moss transition-[width] duration-300"
                          :style="{ width: `${videoUploadState[lesson.id].progress}%` }"
                        />
                      </div>
                      <p class="mt-1 text-xs text-ink-3">
                        Загрузка: {{ videoUploadState[lesson.id].progress }}%. После загрузки видео
                        обрабатывается — страницу можно закрыть.
                      </p>
                    </div>
                    <p v-if="videoUploadState[lesson.id]?.error" class="mt-2 text-sm text-clay">
                      {{ videoUploadState[lesson.id].error }}
                    </p>
                  </section>

                  <section v-show="stepOf(lesson.id) === 'presentation'">
                    <p class="mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-sm font-medium text-ink">
                      <Presentation :size="15" :stroke-width="1.8" class="text-ink-3" />
                      Презентация
                      <span class="font-normal text-ink-3">— ученик видит её рядом с видео</span>
                    </p>
                    <div class="flex flex-wrap items-center gap-2">
                      <span
                        v-if="lesson.presentation_name"
                        class="inline-flex min-h-9 max-w-full items-center gap-1.5 rounded-lg bg-paper-2 px-3 text-sm text-ink"
                      >
                        <span class="truncate" :title="lesson.presentation_name">{{ lesson.presentation_name }}</span>
                        <span class="shrink-0 text-ink-3">{{ formatFileSize(lesson.presentation_size) }}</span>
                      </span>
                      <label
                        class="inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-lg border border-line bg-paper px-3 text-sm font-medium text-ink-2 transition-all duration-200 hover:border-moss/50 hover:text-ink"
                        :class="presentationState[lesson.id]?.uploading ? 'pointer-events-none opacity-50' : ''"
                      >
                        <Plus :size="14" :stroke-width="2" />
                        {{ lesson.presentation_name ? "Заменить" : "Загрузить файл" }}
                        <input
                          type="file"
                          :accept="PRESENTATION_ACCEPT"
                          class="hidden"
                          :disabled="presentationState[lesson.id]?.uploading"
                          @change="handlePresentationFileChange(lesson.id, $event)"
                        />
                      </label>
                      <button
                        v-if="lesson.presentation_name"
                        class="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-line bg-paper px-3 text-sm font-medium text-ink-2 transition-all duration-200 hover:border-moss/50 hover:text-ink"
                        @click="presentationUi(lesson.id).preview = !presentationUi(lesson.id).preview"
                      >
                        {{ presentationState[lesson.id]?.preview ? "Скрыть просмотр" : "Посмотреть как ученик" }}
                      </button>
                      <button
                        v-if="lesson.presentation_name"
                        class="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-line bg-paper px-3 text-sm font-medium text-clay transition-all duration-200 hover:border-clay/40 disabled:opacity-50"
                        :disabled="presentationState[lesson.id]?.uploading"
                        @click="handleDeletePresentation(lesson.id)"
                      >
                        <Trash2 :size="14" :stroke-width="1.8" />
                        Удалить
                      </button>
                    </div>
                    <div v-if="presentationState[lesson.id]?.uploading" class="mt-2">
                      <div class="h-1.5 overflow-hidden rounded-full bg-paper-2">
                        <div
                          class="h-full rounded-full bg-moss transition-[width] duration-300"
                          :style="{ width: `${presentationState[lesson.id].progress}%` }"
                        />
                      </div>
                      <p class="mt-1 text-xs text-ink-3">Загрузка: {{ presentationState[lesson.id].progress }}%</p>
                    </div>
                    <p v-if="presentationState[lesson.id]?.error" class="mt-2 text-sm text-clay">
                      {{ presentationState[lesson.id].error }}
                    </p>
                    <p v-if="!lesson.presentation_name" class="mt-2 text-xs text-ink-3">
                      PowerPoint (.pptx, .ppsx) или PDF, до 10 МБ. В PowerPoint сохраняются дизайн и анимации;
                      чтобы шрифты не подменились, при сохранении включите «Внедрить шрифты в файл». PDF
                      показывается без анимаций. Ученик сможет скачать файл.
                    </p>
                    <PresentationViewer
                      v-if="lesson.presentation_name && presentationState[lesson.id]?.preview"
                      :key="lesson.presentation_name + (lesson.presentation_size ?? '')"
                      class="mt-3"
                      :name="lesson.presentation_name"
                      :size="lesson.presentation_size"
                      :load-link="() => getTeacherPresentationLink(lesson.id)"
                    />
                  </section>

                  <section v-show="stepOf(lesson.id) === 'test'">
                    <p class="mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-sm font-medium text-ink">
                      <ListChecks :size="15" :stroke-width="1.8" class="text-ink-3" />
                      Мини-тест урока
                      <span class="font-normal text-ink-3">— ученик проходит после видео</span>
                    </p>
                    <QuestionBank
                      :lesson-id="lesson.id"
                      :per-attempt="lesson.questions_per_attempt ?? null"
                      @per-attempt-saved="lesson.questions_per_attempt = $event"
                    />
                  </section>

                  <section v-show="stepOf(lesson.id) === 'homework'">
                    <p class="mb-2 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-sm font-medium text-ink">
                      <ClipboardCheck :size="15" :stroke-width="1.8" class="text-ink-3" />
                      Домашнее задание с автопроверкой
                      <span class="font-normal text-ink-3">— пропуски, тесты, эссе, фото; сроки и попытки</span>
                    </p>
                    <HwBuilder :lesson-id="lesson.id" @changed="refreshLessonSummaries" />
                  </section>

                  <div class="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-4">
                    <button
                      v-if="stepIndex(lesson.id) > 0"
                      type="button"
                      class="min-h-12 rounded-xl border-2 border-line px-4 font-semibold text-ink-2 hover:border-moss/40"
                      @click="goStep(lesson.id, -1)"
                    >
                      ← Назад
                    </button>
                    <span v-else />
                    <button
                      v-if="stepIndex(lesson.id) < LESSON_STEPS.length - 1"
                      type="button"
                      class="btn-primary min-h-12 px-5 text-base"
                      @click="goStep(lesson.id, 1)"
                    >
                      Далее: {{ LESSON_STEPS[stepIndex(lesson.id) + 1].label }} →
                    </button>
                    <button v-else type="button" class="btn-primary min-h-12 px-5 text-base" @click="toggleLesson(lesson.id)">
                      Готово — свернуть урок
                    </button>
                  </div>
                </div>
              </div>
            </li>
          </ul>

          <button
            class="inline-flex min-h-10 items-center gap-1.5 rounded-lg border border-dashed border-line-strong px-3 text-sm font-medium text-ink-2 transition-all duration-200 hover:border-moss/50 hover:text-ink"
            @click="openLessonForm(section.id)"
          >
            <Plus :size="15" :stroke-width="2" />
            Добавить урок в раздел
          </button>

          <div v-if="lessonForms[section.id]?.open" class="mt-3 space-y-3 rounded-xl border border-line bg-paper-2 p-4">
            <p class="text-sm font-medium text-ink">Новый урок</p>
            <BaseInput v-model="lessonForms[section.id].title" label="Название урока" :maxlength="200" />
            <BaseInput
              v-model="lessonForms[section.id].video"
              label="Видео с YouTube (необязательно)"
              placeholder="https://www.youtube.com/watch?v=…"
              :maxlength="500"
            />
            <RichTextEditor v-model="lessonForms[section.id].description" label="Описание и теория (видит ученик под видео)" />
            <RichTextEditor
              v-model="lessonForms[section.id].homework"
              label="Домашнее задание"
              min-height="8rem"
            />
            <p class="text-caption text-ink-3">Видео и вопросы можно добавить сразу после сохранения.</p>
            <BaseButton @click="handleCreateLesson(section.id)">Создать урок</BaseButton>
          </div>

          <!-- Тест раздела свёрнут: это отдельная сущность от уроков, и
               развёрнутый банк вопросов раньше удваивал длину каждой секции. -->
          <div class="mt-4 overflow-hidden rounded-xl border border-line">
            <button
              type="button"
              class="flex w-full items-center gap-2 p-3 text-left transition-colors duration-200 hover:bg-paper-2"
              :aria-expanded="openSectionTestIds.has(section.id)"
              @click="toggleSectionTest(section.id)"
            >
              <ListChecks :size="15" :stroke-width="1.8" class="shrink-0 text-ink-3" />
              <span class="min-w-0 flex-1">
                <span class="block text-sm font-medium text-ink">Итоговый тест раздела</span>
                <span class="block text-xs text-ink-3">Открывается ученику после всех уроков раздела</span>
              </span>
              <ChevronDown
                :size="17"
                :stroke-width="2"
                class="shrink-0 text-ink-3 transition-transform duration-200"
                :class="openSectionTestIds.has(section.id) ? 'rotate-180' : ''"
              />
            </button>
            <div v-if="openSectionTestIds.has(section.id)" class="border-t border-line p-3">
              <QuestionBank
                :section-id="section.id"
                :per-attempt="section.questions_per_attempt ?? null"
                @per-attempt-saved="section.questions_per_attempt = $event"
              />
            </div>
          </div>
          </div>
        </div>
      </div>
    </template>
  </PageContainer>
</template>
