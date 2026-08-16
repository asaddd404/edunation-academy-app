<script setup lang="ts">
import { FolderOpen } from "@lucide/vue";
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
import type { Category, Section, VideoStatus } from "@/types";

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

        <div v-for="section in sections" :key="section.id" class="card p-4">
          <div v-if="!sectionEditForms[section.id]?.open" class="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div class="min-w-0">
              <h2 class="text-lg font-medium text-ink">{{ section.title }}</h2>
              <p v-if="section.description" class="text-sm text-ink-2">{{ section.description }}</p>
            </div>
            <div class="flex shrink-0 flex-wrap gap-3">
              <button class="text-sm text-ink-3 hover:text-ink" @click="startEditSection(section)">Редактировать</button>
              <button class="text-sm text-clay hover:brightness-110" @click="handleDeleteSection(section.id)">
                Удалить раздел
              </button>
            </div>
          </div>
          <div v-else class="mb-3 space-y-2 rounded-lg bg-paper-2 p-3">
            <BaseInput v-model="sectionEditForms[section.id].title" label="Название раздела" />
            <BaseInput v-model="sectionEditForms[section.id].description" label="Описание" />
            <div class="flex gap-2">
              <BaseButton @click="saveSection(section.id)">Сохранить</BaseButton>
              <BaseButton variant="secondary" @click="cancelEditSection(section.id)">Отмена</BaseButton>
            </div>
          </div>

          <ul class="mb-3 space-y-3">
            <li v-for="lesson in section.lessons" :key="lesson.id" class="rounded-lg border border-line p-3">
              <div v-if="!lessonEditForms[lesson.id]?.open" class="mb-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <p class="min-w-0 font-medium text-ink">{{ lesson.title }}</p>
                <div class="flex shrink-0 flex-wrap gap-3">
                  <button class="text-sm text-ink-3 hover:text-ink" @click="startEditLesson(lesson.id)">Редактировать</button>
                  <button class="text-sm text-clay hover:brightness-110" @click="handleDeleteLesson(lesson.id)">
                    Удалить
                  </button>
                </div>
              </div>
              <div v-else class="mb-3 space-y-2 rounded-lg bg-paper-2 p-3">
                <p v-if="lessonEditForms[lesson.id].loading" class="text-sm text-ink-2">Загрузка…</p>
                <template v-else>
                  <BaseInput v-model="lessonEditForms[lesson.id].title" label="Название урока" />
                  <RichTextEditor v-model="lessonEditForms[lesson.id].description" label="Описание/теория" />
                  <RichTextEditor
                    v-model="lessonEditForms[lesson.id].homework"
                    label="Задание для домашней работы"
                    min-height="8rem"
                  />
                  <div class="flex gap-2">
                    <BaseButton @click="saveLesson(lesson.id)">Сохранить</BaseButton>
                    <BaseButton variant="secondary" @click="cancelEditLesson(lesson.id)">Отмена</BaseButton>
                  </div>
                </template>
              </div>

              <template v-if="!lessonEditForms[lesson.id]?.open">
                <div class="mb-3 flex flex-wrap items-center gap-2">
                  <BaseBadge :tone="videoStatusTone[lesson.video_status]">{{ videoStatusLabel[lesson.video_status] }}</BaseBadge>
                  <label class="cursor-pointer text-sm text-moss underline">
                    {{ lesson.video_status === "none" ? "Загрузить видео" : "Заменить видео" }}
                    <input
                      type="file"
                      accept="video/*"
                      class="hidden"
                      :disabled="videoUploadState[lesson.id]?.uploading"
                      @change="handleVideoFileChange(lesson.id, $event)"
                    />
                  </label>
                  <BaseButton
                    v-if="lesson.video_status !== 'none'"
                    variant="secondary"
                    :disabled="videoUploadState[lesson.id]?.uploading"
                    @click="handleDeleteVideo(lesson.id)"
                  >
                    Удалить видео
                  </BaseButton>
                  <span v-if="videoUploadState[lesson.id]?.uploading" class="text-sm text-ink-2">
                    Загрузка: {{ videoUploadState[lesson.id].progress }}%
                  </span>
                  <span v-if="videoUploadState[lesson.id]?.error" class="text-sm text-clay">
                    {{ videoUploadState[lesson.id].error }}
                  </span>
                </div>

                <div class="mt-3">
                  <p class="mb-2 text-sm font-medium text-ink-2">Мини-тест урока</p>
                  <QuestionBank :lesson-id="lesson.id" />
                </div>
              </template>
            </li>
          </ul>

          <BaseButton variant="secondary" @click="openLessonForm(section.id)">Добавить урок</BaseButton>

          <div v-if="lessonForms[section.id]?.open" class="mt-3 space-y-2 rounded-lg bg-paper-2 p-3">
            <BaseInput v-model="lessonForms[section.id].title" label="Название урока" />
            <RichTextEditor v-model="lessonForms[section.id].description" label="Описание/теория" />
            <RichTextEditor
              v-model="lessonForms[section.id].homework"
              label="Задание для домашней работы"
              min-height="8rem"
            />
            <BaseButton @click="handleCreateLesson(section.id)">Сохранить урок</BaseButton>
          </div>

          <div class="mt-4 border-t border-line pt-4">
            <p class="mb-2 text-sm text-ink-2">Тест раздела (открывается после всех уроков)</p>
            <QuestionBank :section-id="section.id" />
          </div>
        </div>
      </div>
    </template>
  </PageContainer>
</template>
