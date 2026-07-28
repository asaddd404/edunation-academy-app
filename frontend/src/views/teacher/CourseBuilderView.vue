<script setup lang="ts">
import { reactive, ref } from "vue";
import { onMounted } from "vue";
import { useRoute } from "vue-router";

import { createLesson, createQuestion } from "@/api/lessons";
import { createSection, listTeacherSections } from "@/api/sections";
import BaseButton from "@/components/ui/BaseButton.vue";
import BaseInput from "@/components/ui/BaseInput.vue";
import type { Section } from "@/types";

const route = useRoute();
const categoryId = Number(route.params.id);

const sections = ref<Section[]>([]);
const loading = ref(true);

const newSectionTitle = ref("");
const newSectionDescription = ref("");

const lessonForms = reactive<Record<number, { title: string; description: string; videoUrl: string; homework: string; open: boolean }>>({});
const questionForms = reactive<Record<number, { text: string; choices: { text: string; isCorrect: boolean }[]; open: boolean }>>({});

async function load() {
  loading.value = true;
  sections.value = await listTeacherSections(categoryId);
  loading.value = false;
}

onMounted(load);

async function handleCreateSection() {
  if (!newSectionTitle.value.trim()) return;
  await createSection(categoryId, { title: newSectionTitle.value, description: newSectionDescription.value || undefined });
  newSectionTitle.value = "";
  newSectionDescription.value = "";
  await load();
}

function openLessonForm(sectionId: number) {
  lessonForms[sectionId] = { title: "", description: "", videoUrl: "", homework: "", open: true };
}

async function handleCreateLesson(sectionId: number) {
  const form = lessonForms[sectionId];
  if (!form?.title.trim()) return;
  await createLesson(sectionId, {
    title: form.title,
    description: form.description || undefined,
    video_url: form.videoUrl || undefined,
    homework_assignment: form.homework || undefined,
  });
  lessonForms[sectionId] = { title: "", description: "", videoUrl: "", homework: "", open: false };
  await load();
}

function openQuestionForm(lessonId: number) {
  questionForms[lessonId] = {
    text: "",
    choices: [
      { text: "", isCorrect: true },
      { text: "", isCorrect: false },
    ],
    open: true,
  };
}

function addChoice(lessonId: number) {
  const form = questionForms[lessonId];
  if (form.choices.length < 6) form.choices.push({ text: "", isCorrect: false });
}

async function handleCreateQuestion(lessonId: number) {
  const form = questionForms[lessonId];
  if (!form?.text.trim() || form.choices.some((c) => !c.text.trim())) return;
  await createQuestion(lessonId, {
    text: form.text,
    choices: form.choices.map((c) => ({ text: c.text, is_correct: c.isCorrect })),
  });
  questionForms[lessonId] = { text: "", choices: [], open: false };
  await load();
}
</script>

<template>
  <div>
    <h1 class="mb-6 text-2xl font-semibold">Конструктор курса</h1>
    <p v-if="loading" class="text-fg/60">Загрузка…</p>
    <div v-else class="space-y-6">
      <form class="flex flex-col gap-3 rounded-xl border border-fg/10 p-4 sm:flex-row sm:items-end" @submit.prevent="handleCreateSection">
        <BaseInput v-model="newSectionTitle" label="Новый раздел" class="flex-1" />
        <BaseInput v-model="newSectionDescription" label="Описание" class="flex-1" />
        <BaseButton type="submit">Добавить</BaseButton>
      </form>

      <div v-for="section in sections" :key="section.id" class="rounded-xl border border-fg/10 p-4">
        <h2 class="mb-3 text-lg font-medium">{{ section.title }}</h2>

        <ul class="mb-3 space-y-3">
          <li v-for="lesson in section.lessons" :key="lesson.id" class="rounded-lg border border-fg/10 p-3">
            <p class="mb-2 font-medium">{{ lesson.title }}</p>
            <BaseButton variant="secondary" @click="openQuestionForm(lesson.id)">Добавить вопрос</BaseButton>

            <div v-if="questionForms[lesson.id]?.open" class="mt-3 space-y-2 rounded-lg bg-fg/5 p-3">
              <BaseInput v-model="questionForms[lesson.id].text" label="Текст вопроса" />
              <div v-for="(choice, i) in questionForms[lesson.id].choices" :key="i" class="flex items-center gap-2">
                <input type="radio" :name="`correct-${lesson.id}`" :checked="choice.isCorrect" @change="questionForms[lesson.id].choices.forEach((c, ci) => (c.isCorrect = ci === i))" />
                <input v-model="choice.text" placeholder="Вариант ответа" class="flex-1 rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm" />
              </div>
              <div class="flex gap-2">
                <BaseButton variant="secondary" @click="addChoice(lesson.id)">+ вариант</BaseButton>
                <BaseButton @click="handleCreateQuestion(lesson.id)">Сохранить вопрос</BaseButton>
              </div>
            </div>
          </li>
        </ul>

        <BaseButton variant="secondary" @click="openLessonForm(section.id)">Добавить урок</BaseButton>

        <div v-if="lessonForms[section.id]?.open" class="mt-3 space-y-2 rounded-lg bg-fg/5 p-3">
          <BaseInput v-model="lessonForms[section.id].title" label="Название урока" />
          <BaseInput v-model="lessonForms[section.id].description" label="Описание/теория" />
          <BaseInput v-model="lessonForms[section.id].videoUrl" label="Ссылка на видео (заглушка)" />
          <BaseInput v-model="lessonForms[section.id].homework" label="Задание для домашней работы" />
          <BaseButton @click="handleCreateLesson(section.id)">Сохранить урок</BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>
