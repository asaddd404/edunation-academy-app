<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";

import { submitHomework } from "@/api/homework";
import { getLesson, submitTestAttempt } from "@/api/lessons";
import { getStudentVideoTicket } from "@/api/video";
import HlsPlayer from "@/components/media/HlsPlayer.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { AnswerPayload, LessonDetail, TestAttemptResult } from "@/types";

const route = useRoute();
const lessonId = Number(route.params.id);

const lesson = ref<LessonDetail | null>(null);
const loading = ref(true);
const loadError = ref("");

const videoSrc = ref<string | null>(null);
const videoError = ref("");

const answers = reactive<Record<number, AnswerPayload>>({});
const testResult = ref<TestAttemptResult | null>(null);
const testSubmitting = ref(false);
const testError = ref("");

const homeworkText = ref("");
const homeworkFile = ref<File | null>(null);
const homeworkSubmitting = ref(false);
const homeworkError = ref("");

function isAnswered(questionId: number): boolean {
  const a = answers[questionId];
  if (!a) return false;
  if (a.choice_id !== undefined) return true;
  if (a.choice_ids !== undefined) return a.choice_ids.length > 0;
  if (a.pairs !== undefined) return Object.keys(a.pairs).length > 0;
  if (a.text !== undefined) return a.text.trim().length > 0;
  return false;
}

const allQuestionsAnswered = computed(() => {
  if (!lesson.value) return false;
  return lesson.value.questions.every((q) => isAnswered(q.id));
});

function setSingleChoice(questionId: number, choiceId: number) {
  answers[questionId] = { question_id: questionId, choice_id: choiceId };
}

function toggleMultipleChoice(questionId: number, choiceId: number, checked: boolean) {
  const current = answers[questionId] ?? { question_id: questionId, choice_ids: [] };
  const list = current.choice_ids ?? [];
  current.choice_ids = checked ? [...list, choiceId] : list.filter((id) => id !== choiceId);
  answers[questionId] = current;
}

function setMatchPair(questionId: number, promptId: number, answerId: number) {
  const current = answers[questionId] ?? { question_id: questionId, pairs: {} };
  current.pairs = { ...(current.pairs ?? {}), [String(promptId)]: answerId };
  answers[questionId] = current;
}

function setShortAnswer(questionId: number, text: string) {
  answers[questionId] = { question_id: questionId, text };
}

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    lesson.value = await getLesson(lessonId);
    homeworkText.value = lesson.value.my_homework?.text_answer ?? "";
    if (lesson.value.video_status === "ready") {
      try {
        const ticket = await getStudentVideoTicket(lessonId);
        videoSrc.value = `${import.meta.env.VITE_API_BASE_URL}${ticket.playback_path}`;
      } catch {
        videoError.value = "Не удалось загрузить видео.";
      }
    }
  } catch {
    loadError.value = "Урок недоступен — возможно, он ещё заблокирован.";
  } finally {
    loading.value = false;
  }
}

onMounted(load);

async function handleSubmitTest() {
  if (!lesson.value) return;
  testSubmitting.value = true;
  testError.value = "";
  try {
    testResult.value = await submitTestAttempt(lessonId, Object.values(answers));
    if (testResult.value.passed) {
      lesson.value.is_passed = true;
    }
  } catch {
    testError.value = "Не удалось отправить тест. Попробуйте ещё раз.";
  } finally {
    testSubmitting.value = false;
  }
}

async function handleSubmitHomework() {
  homeworkSubmitting.value = true;
  homeworkError.value = "";
  try {
    const submission = await submitHomework(lessonId, homeworkText.value, homeworkFile.value);
    if (lesson.value) lesson.value.my_homework = submission;
    homeworkFile.value = null;
  } catch {
    homeworkError.value = "Не удалось отправить домашнее задание.";
  } finally {
    homeworkSubmitting.value = false;
  }
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  homeworkFile.value = input.files?.[0] ?? null;
}
</script>

<template>
  <div class="mx-auto max-w-2xl space-y-8">
    <p v-if="loading" class="text-fg/60">Загрузка…</p>
    <p v-else-if="loadError" class="text-red-600 dark:text-red-500">{{ loadError }}</p>
    <template v-else-if="lesson">
      <div>
        <h1 class="mb-2 text-2xl font-semibold">{{ lesson.title }}</h1>
        <BaseBadge :tone="lesson.is_passed ? 'success' : 'neutral'">
          {{ lesson.is_passed ? "Тест пройден" : "Тест не пройден" }}
        </BaseBadge>
      </div>

      <HlsPlayer v-if="videoSrc" :src="videoSrc" />
      <p v-else-if="lesson.video_status === 'processing'" class="rounded-xl border border-fg/10 p-4 text-sm text-fg/60">
        Видео обрабатывается, зайдите чуть позже.
      </p>
      <p v-else-if="lesson.video_status === 'failed'" class="rounded-xl border border-fg/10 p-4 text-sm text-red-600 dark:text-red-500">
        Не удалось обработать видео. Сообщите учителю.
      </p>
      <p v-else-if="videoError" class="rounded-xl border border-fg/10 p-4 text-sm text-red-600 dark:text-red-500">{{ videoError }}</p>

      <p v-if="lesson.description" class="whitespace-pre-line text-fg/80">{{ lesson.description }}</p>

      <section v-if="lesson.questions.length" class="space-y-4 rounded-2xl border border-border bg-card p-4 transition-all duration-200">
        <h2 class="text-lg font-medium">Мини-тест</h2>
        <div v-for="question in lesson.questions" :key="question.id" class="space-y-2">
          <p class="font-medium">{{ question.text }}</p>

          <template v-if="question.qtype === 'single'">
            <label
              v-for="choice in question.choices"
              :key="choice.id"
              class="flex items-center gap-2 rounded-lg border border-fg/10 px-3 py-2 text-sm"
            >
              <input
                type="radio"
                :name="`question-${question.id}`"
                :value="choice.id"
                @change="setSingleChoice(question.id, choice.id)"
              />
              {{ choice.text }}
            </label>
          </template>

          <template v-else-if="question.qtype === 'multiple'">
            <label
              v-for="choice in question.choices"
              :key="choice.id"
              class="flex items-center gap-2 rounded-lg border border-fg/10 px-3 py-2 text-sm"
            >
              <input
                type="checkbox"
                @change="toggleMultipleChoice(question.id, choice.id, ($event.target as HTMLInputElement).checked)"
              />
              {{ choice.text }}
            </label>
          </template>

          <template v-else-if="question.qtype === 'matching'">
            <div v-for="prompt in question.match_prompts" :key="prompt.id" class="flex items-center gap-2 text-sm">
              <span class="w-1/2">{{ prompt.text }}</span>
              <select
                class="w-1/2 rounded-lg border border-fg/20 bg-transparent px-3 py-2"
                @change="setMatchPair(question.id, prompt.id, Number(($event.target as HTMLSelectElement).value))"
              >
                <option value="" disabled selected>Выберите пару</option>
                <option v-for="opt in question.match_answers" :key="opt.id" :value="opt.id">{{ opt.text }}</option>
              </select>
            </div>
          </template>

          <template v-else>
            <input
              type="text"
              placeholder="Ваш ответ"
              class="w-full rounded-lg border border-fg/20 bg-transparent px-4 py-2.5 text-sm"
              @input="setShortAnswer(question.id, ($event.target as HTMLInputElement).value)"
            />
          </template>
        </div>
        <p v-if="testResult" class="text-sm" :class="testResult.passed ? 'text-green-700 dark:text-green-500' : 'text-red-600 dark:text-red-500'">
          {{
            testResult.passed
              ? `Тест пройден, балл: ${testResult.score}%`
              : `Тест не пройден (балл: ${testResult.score}%). Правильные ответы не показываются — пересмотрите урок и попробуйте снова.`
          }}
        </p>
        <p v-if="testError" class="text-sm text-red-600 dark:text-red-500">{{ testError }}</p>
        <BaseButton variant="cta" :disabled="!allQuestionsAnswered || testSubmitting" @click="handleSubmitTest">
          Отправить тест
        </BaseButton>
      </section>

      <section v-if="lesson.homework_assignment" class="space-y-3 rounded-2xl border border-border bg-card p-4 transition-all duration-200">
        <h2 class="text-lg font-medium">Домашнее задание</h2>
        <p class="text-fg/80">{{ lesson.homework_assignment }}</p>

        <div v-if="lesson.my_homework" class="rounded-lg bg-fg/5 p-3 text-sm">
          <p>
            Статус:
            <BaseBadge
              :tone="
                lesson.my_homework.status === 'accepted'
                  ? 'success'
                  : lesson.my_homework.status === 'revision_requested'
                    ? 'danger'
                    : 'warning'
              "
            >
              {{
                lesson.my_homework.status === "accepted"
                  ? "Принято"
                  : lesson.my_homework.status === "revision_requested"
                    ? "На доработку"
                    : "На проверке"
              }}
            </BaseBadge>
          </p>
          <p v-if="lesson.my_homework.teacher_feedback" class="mt-2">
            Комментарий учителя: {{ lesson.my_homework.teacher_feedback }}
          </p>
        </div>

        <textarea
          v-model="homeworkText"
          rows="4"
          placeholder="Текст ответа…"
          class="w-full rounded-lg border border-fg/20 bg-transparent px-4 py-3 text-sm focus:border-accent focus:outline-none"
        />
        <input type="file" accept=".jpg,.jpeg,.png,.pdf,.txt,.doc,.docx" class="text-sm" @change="handleFileChange" />
        <p v-if="homeworkError" class="text-sm text-red-600 dark:text-red-500">{{ homeworkError }}</p>
        <BaseButton variant="cta" :disabled="homeworkSubmitting" @click="handleSubmitHomework">
          Отправить домашку
        </BaseButton>
      </section>
    </template>
  </div>
</template>
