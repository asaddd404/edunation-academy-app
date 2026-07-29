<script setup lang="ts">
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

onMounted(async () => {
  category.value = await getTeacherCategory(categoryId);
  await load();
});

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
  <div>
    <h1 class="mb-6 text-2xl font-semibold">Конструктор курса</h1>

    <div v-if="category" class="mb-6 flex flex-col gap-4 rounded-xl border border-fg/10 p-4 sm:flex-row">
      <img
        v-if="category.has_image"
        :src="`${getCategoryImageUrl(categoryId)}?v=${categoryImageCacheBust}`"
        alt=""
        class="h-28 w-28 shrink-0 rounded-lg object-cover"
      />
      <div class="flex-1">
        <h2 class="text-lg font-medium">{{ category.name }}</h2>
        <div v-if="!categoryDescEditing">
          <p class="mt-1 text-sm text-fg/60">{{ category.description || "Описание не задано" }}</p>
          <button class="mt-2 text-sm text-accent underline" @click="startEditCategoryDescription">
            Редактировать описание
          </button>
        </div>
        <div v-else class="mt-2 space-y-2">
          <textarea
            v-model="categoryDescDraft"
            rows="3"
            class="w-full rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm focus:border-accent focus:outline-none"
          />
          <div class="flex gap-2">
            <BaseButton @click="saveCategoryDescription">Сохранить</BaseButton>
            <BaseButton variant="secondary" @click="categoryDescEditing = false">Отмена</BaseButton>
          </div>
        </div>

        <div class="mt-3 flex flex-wrap items-center gap-2">
          <label class="cursor-pointer text-sm text-accent underline">
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
          <span v-if="categoryImageUploading" class="text-sm text-fg/60">Загрузка…</span>
          <span v-if="categoryImageError" class="text-sm text-red-500">{{ categoryImageError }}</span>
        </div>
      </div>
    </div>

    <p v-if="loading" class="text-fg/60">Загрузка…</p>
    <div v-else class="space-y-6">
      <form class="flex flex-col gap-3 rounded-xl border border-fg/10 p-4 sm:flex-row sm:items-end" @submit.prevent="handleCreateSection">
        <BaseInput v-model="newSectionTitle" label="Новый раздел" class="flex-1" />
        <BaseInput v-model="newSectionDescription" label="Описание" class="flex-1" />
        <BaseButton type="submit">Добавить</BaseButton>
      </form>

      <div v-for="section in sections" :key="section.id" class="rounded-xl border border-fg/10 p-4">
        <div v-if="!sectionEditForms[section.id]?.open" class="mb-3 flex items-center justify-between gap-2">
          <div>
            <h2 class="text-lg font-medium">{{ section.title }}</h2>
            <p v-if="section.description" class="text-sm text-fg/60">{{ section.description }}</p>
          </div>
          <div class="flex shrink-0 gap-3">
            <button class="text-sm text-fg/50 hover:text-fg" @click="startEditSection(section)">Редактировать</button>
            <button class="text-sm text-red-500 hover:text-red-600" @click="handleDeleteSection(section.id)">
              Удалить раздел
            </button>
          </div>
        </div>
        <div v-else class="mb-3 space-y-2 rounded-lg bg-fg/5 p-3">
          <BaseInput v-model="sectionEditForms[section.id].title" label="Название раздела" />
          <BaseInput v-model="sectionEditForms[section.id].description" label="Описание" />
          <div class="flex gap-2">
            <BaseButton @click="saveSection(section.id)">Сохранить</BaseButton>
            <BaseButton variant="secondary" @click="cancelEditSection(section.id)">Отмена</BaseButton>
          </div>
        </div>

        <ul class="mb-3 space-y-3">
          <li v-for="lesson in section.lessons" :key="lesson.id" class="rounded-lg border border-fg/10 p-3">
            <div v-if="!lessonEditForms[lesson.id]?.open" class="mb-2 flex items-center justify-between gap-2">
              <p class="font-medium">{{ lesson.title }}</p>
              <div class="flex shrink-0 gap-3">
                <button class="text-sm text-fg/50 hover:text-fg" @click="startEditLesson(lesson.id)">Редактировать</button>
                <button class="text-sm text-red-500 hover:text-red-600" @click="handleDeleteLesson(lesson.id)">
                  Удалить
                </button>
              </div>
            </div>
            <div v-else class="mb-3 space-y-2 rounded-lg bg-fg/5 p-3">
              <p v-if="lessonEditForms[lesson.id].loading" class="text-sm text-fg/60">Загрузка…</p>
              <template v-else>
                <BaseInput v-model="lessonEditForms[lesson.id].title" label="Название урока" />
                <BaseInput v-model="lessonEditForms[lesson.id].description" label="Описание/теория" />
                <BaseInput v-model="lessonEditForms[lesson.id].homework" label="Задание для домашней работы" />
                <div class="flex gap-2">
                  <BaseButton @click="saveLesson(lesson.id)">Сохранить</BaseButton>
                  <BaseButton variant="secondary" @click="cancelEditLesson(lesson.id)">Отмена</BaseButton>
                </div>
              </template>
            </div>

            <template v-if="!lessonEditForms[lesson.id]?.open">
              <div class="mb-3 flex flex-wrap items-center gap-2">
                <BaseBadge :tone="videoStatusTone[lesson.video_status]">{{ videoStatusLabel[lesson.video_status] }}</BaseBadge>
                <label class="cursor-pointer text-sm text-accent underline">
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
                <span v-if="videoUploadState[lesson.id]?.uploading" class="text-sm text-fg/60">
                  Загрузка: {{ videoUploadState[lesson.id].progress }}%
                </span>
                <span v-if="videoUploadState[lesson.id]?.error" class="text-sm text-red-500">
                  {{ videoUploadState[lesson.id].error }}
                </span>
              </div>

              <div class="mt-3">
                <p class="mb-2 text-sm font-medium text-fg/80">Мини-тест урока</p>
                <QuestionBank :lesson-id="lesson.id" />
              </div>
            </template>
          </li>
        </ul>

        <BaseButton variant="secondary" @click="openLessonForm(section.id)">Добавить урок</BaseButton>

        <div v-if="lessonForms[section.id]?.open" class="mt-3 space-y-2 rounded-lg bg-fg/5 p-3">
          <BaseInput v-model="lessonForms[section.id].title" label="Название урока" />
          <BaseInput v-model="lessonForms[section.id].description" label="Описание/теория" />
          <BaseInput v-model="lessonForms[section.id].homework" label="Задание для домашней работы" />
          <BaseButton @click="handleCreateLesson(section.id)">Сохранить урок</BaseButton>
        </div>

        <div class="mt-4 border-t border-fg/10 pt-4">
          <p class="mb-2 text-sm text-fg/60">Тест раздела (открывается после всех уроков)</p>
          <QuestionBank :section-id="section.id" />
        </div>
      </div>
    </div>
  </div>
</template>
