<script setup lang="ts">
import {
  ChevronDown,
  CircleCheck,
  FileText,
  FolderOpen,
  ListChecks,
  Pencil,
  Plus,
  Trash2,
  Video,
} from "@lucide/vue";
import { onBeforeUnmount, onMounted, reactive, ref } from "vue";
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
import { deleteLessonVideo, getTeacherLesson, uploadLessonVideo } from "@/api/video";
import QuestionBank from "@/components/course/QuestionBank.vue";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import RichTextEditor from "@/components/richtext/RichTextEditor.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import BaseInput from "@/components/ui/BaseInput.vue";
import type { Category, LessonSummary, Section, VideoStatus } from "@/types";
import { pluralRu } from "@/utils/subjectTheme";

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

const lessonForms = reactive<Record<number, { title: string; description: string; homework: string; open: boolean }>>({});
const videoUploadState = reactive<Record<number, { uploading: boolean; progress: number; error: string }>>({});
const pollTimers: Record<number, ReturnType<typeof setTimeout>> = {};

const sectionEditForms = reactive<Record<number, { title: string; description: string; open: boolean }>>({});
const lessonEditForms = reactive<
  Record<number, { title: string; description: string; homework: string; open: boolean; loading: boolean }>
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
      label: lesson.video_status === "ready" ? "Видео" : videoStatusLabel[lesson.video_status],
      done: lesson.video_status === "ready",
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
      label: lesson.has_homework ? "Домашка" : "Без домашки",
      done: lesson.has_homework,
    },
  ];
}

function lessonIsReady(lesson: LessonSummary): boolean {
  return lesson.video_status === "ready" && lesson.question_count > 0;
}

async function load() {
  loading.value = true;
  sections.value = await listTeacherSections(categoryId);
  loading.value = false;
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

async function saveSection(sectionId: number) {
  const form = sectionEditForms[sectionId];
  if (!form.title.trim()) return;
  await updateSection(sectionId, { title: form.title, description: form.description || undefined });
  form.open = false;
  await load();
}

async function handleDeleteSection(sectionId: number) {
  if (!confirm("Удалить раздел и все его уроки? Это действие необратимо.")) return;
  await deleteSection(sectionId);
  await load();
}

async function startEditLesson(lessonId: number) {
  lessonEditForms[lessonId] = { title: "", description: "", homework: "", open: true, loading: true };
  const full = await getTeacherLesson(lessonId);
  lessonEditForms[lessonId] = {
    title: full.title,
    description: full.description ?? "",
    homework: full.homework_assignment ?? "",
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
  await updateLesson(lessonId, {
    title: form.title,
    description: form.description || undefined,
    homework_assignment: form.homework || undefined,
  });
  form.open = false;
  await load();
}

async function handleDeleteLesson(lessonId: number) {
  if (!confirm("Удалить урок вместе с видео, вопросами и домашкой? Это действие необратимо.")) return;
  await deleteLesson(lessonId);
  await load();
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

async function handleDeleteVideo(lessonId: number) {
  await deleteLessonVideo(lessonId);
  setLessonVideoStatus(lessonId, "none");
}

async function handleCreateSection() {
  if (!newSectionTitle.value.trim()) return;
  await createSection(categoryId, { title: newSectionTitle.value, description: newSectionDescription.value || undefined });
  newSectionTitle.value = "";
  newSectionDescription.value = "";
  await load();
}

function openLessonForm(sectionId: number) {
  lessonForms[sectionId] = { title: "", description: "", homework: "", open: true };
}

async function handleCreateLesson(sectionId: number) {
  const form = lessonForms[sectionId];
  if (!form?.title.trim()) return;
  await createLesson(sectionId, {
    title: form.title,
    description: form.description || undefined,
    homework_assignment: form.homework || undefined,
  });
  lessonForms[sectionId] = { title: "", description: "", homework: "", open: false };
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
          <BaseInput v-model="newSectionTitle" label="Новый раздел" class="flex-1" />
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
            <BaseInput v-model="sectionEditForms[section.id].title" label="Название раздела" />
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
                  <span class="block truncate font-medium text-ink">{{ lesson.title }}</span>
                  <span class="mt-1 flex flex-wrap gap-1.5">
                    <span
                      v-for="chip in lessonChips(lesson)"
                      :key="chip.key"
                      class="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-medium"
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
                  <BaseInput v-model="lessonEditForms[lesson.id].title" label="Название урока" />
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

                <div class="space-y-4 p-3">
                  <section>
                    <p class="mb-2 flex items-center gap-1.5 text-sm font-medium text-ink">
                      <Video :size="15" :stroke-width="1.8" class="text-ink-3" />
                      Видеоурок
                    </p>
                    <div class="flex flex-wrap items-center gap-2">
                      <BaseBadge :tone="videoStatusTone[lesson.video_status]">
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

                  <section class="border-t border-line pt-3">
                    <p class="mb-2 flex items-center gap-1.5 text-sm font-medium text-ink">
                      <ListChecks :size="15" :stroke-width="1.8" class="text-ink-3" />
                      Мини-тест урока
                      <span class="font-normal text-ink-3">— ученик проходит после видео</span>
                    </p>
                    <QuestionBank :lesson-id="lesson.id" />
                  </section>
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
            <BaseInput v-model="lessonForms[section.id].title" label="Название урока" />
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
              <QuestionBank :section-id="section.id" />
            </div>
          </div>
          </div>
        </div>
      </div>
    </template>
  </PageContainer>
</template>
