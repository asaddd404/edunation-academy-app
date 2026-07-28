<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import { submitHomework } from "@/api/homework";
import { getLesson, submitTestAttempt } from "@/api/lessons";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { LessonDetail, TestAttemptResult } from "@/types";

const route = useRoute();
const lessonId = Number(route.params.id);

const lesson = ref<LessonDetail | null>(null);
const loading = ref(true);
const loadError = ref("");

const answers = ref<Record<number, number>>({});
const testResult = ref<TestAttemptResult | null>(null);
const testSubmitting = ref(false);
const testError = ref("");

const homeworkText = ref("");
const homeworkFile = ref<File | null>(null);
const homeworkSubmitting = ref(false);
const homeworkError = ref("");

const allQuestionsAnswered = computed(() => {
  if (!lesson.value) return false;
  return lesson.value.questions.every((q) => answers.value[q.id] !== undefined);
});

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    lesson.value = await getLesson(lessonId);
    homeworkText.value = lesson.value.my_homework?.text_answer ?? "";
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
    const payload = Object.entries(answers.value).map(([questionId, choiceId]) => ({
      question_id: Number(questionId),
      choice_id: choiceId,
    }));
    testResult.value = await submitTestAttempt(lessonId, payload);
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
    <p v-else-if="loadError" class="text-red-500">{{ loadError }}</p>
    <template v-else-if="lesson">
      <div>
        <h1 class="mb-2 text-2xl font-semibold">{{ lesson.title }}</h1>
        <BaseBadge :tone="lesson.is_passed ? 'success' : 'neutral'">
          {{ lesson.is_passed ? "Тест пройден" : "Тест не пройден" }}
        </BaseBadge>
      </div>

      <div v-if="lesson.video_url" class="rounded-xl border border-fg/10 p-4 text-sm text-fg/60">
        Видео появится здесь позже. Пока ссылка: {{ lesson.video_url }}
      </div>

      <p v-if="lesson.description" class="whitespace-pre-line text-fg/80">{{ lesson.description }}</p>

      <section v-if="lesson.questions.length" class="space-y-4 rounded-xl border border-fg/10 p-4">
        <h2 class="text-lg font-medium">Мини-тест</h2>
        <div v-for="question in lesson.questions" :key="question.id" class="space-y-2">
          <p class="font-medium">{{ question.text }}</p>
          <label
            v-for="choice in question.choices"
            :key="choice.id"
            class="flex items-center gap-2 rounded-lg border border-fg/10 px-3 py-2 text-sm"
          >
            <input
              type="radio"
              :name="`question-${question.id}`"
              :value="choice.id"
              @change="answers[question.id] = choice.id"
            />
            {{ choice.text }}
          </label>
        </div>
        <p v-if="testResult" class="text-sm" :class="testResult.passed ? 'text-green-500' : 'text-red-500'">
          {{
            testResult.passed
              ? `Тест пройден, балл: ${testResult.score}%`
              : `Тест не пройден (балл: ${testResult.score}%). Правильные ответы не показываются — пересмотрите урок и попробуйте снова.`
          }}
        </p>
        <p v-if="testError" class="text-sm text-red-500">{{ testError }}</p>
        <BaseButton :disabled="!allQuestionsAnswered || testSubmitting" @click="handleSubmitTest">
          Отправить тест
        </BaseButton>
      </section>

      <section v-if="lesson.homework_assignment" class="space-y-3 rounded-xl border border-fg/10 p-4">
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
        <p v-if="homeworkError" class="text-sm text-red-500">{{ homeworkError }}</p>
        <BaseButton :disabled="homeworkSubmitting" @click="handleSubmitHomework">Отправить домашку</BaseButton>
      </section>
    </template>
  </div>
</template>
