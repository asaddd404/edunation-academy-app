<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import { getSectionTest, submitSectionTestAttempt } from "@/api/sections";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { SectionTest, TestAttemptResult } from "@/types";

const route = useRoute();
const sectionId = Number(route.params.id);

const test = ref<SectionTest | null>(null);
const loading = ref(true);
const loadError = ref("");

const answers = ref<Record<number, number>>({});
const result = ref<TestAttemptResult | null>(null);
const submitting = ref(false);
const submitError = ref("");

const allQuestionsAnswered = computed(() => {
  if (!test.value) return false;
  return test.value.questions.every((q) => answers.value[q.id] !== undefined);
});

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    test.value = await getSectionTest(sectionId);
  } catch {
    loadError.value = "Тест раздела недоступен — возможно, пройдены не все уроки.";
  } finally {
    loading.value = false;
  }
}

onMounted(load);

async function handleSubmit() {
  if (!test.value) return;
  submitting.value = true;
  submitError.value = "";
  try {
    const payload = Object.entries(answers.value).map(([questionId, choiceId]) => ({
      question_id: Number(questionId),
      choice_id: choiceId,
    }));
    result.value = await submitSectionTestAttempt(sectionId, payload);
    if (result.value.passed) test.value.is_passed = true;
  } catch {
    submitError.value = "Не удалось отправить тест. Попробуйте ещё раз.";
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="mx-auto max-w-2xl space-y-6">
    <p v-if="loading" class="text-fg/60">Загрузка…</p>
    <p v-else-if="loadError" class="text-red-500">{{ loadError }}</p>
    <template v-else-if="test">
      <div>
        <h1 class="mb-2 text-2xl font-semibold">Тест раздела</h1>
        <BaseBadge :tone="test.is_passed ? 'success' : 'neutral'">
          {{ test.is_passed ? "Пройден" : "Не пройден" }}
        </BaseBadge>
      </div>

      <section class="space-y-4 rounded-xl border border-fg/10 p-4">
        <div v-for="question in test.questions" :key="question.id" class="space-y-2">
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
        <p v-if="result" class="text-sm" :class="result.passed ? 'text-green-500' : 'text-red-500'">
          {{
            result.passed
              ? `Тест пройден, балл: ${result.score}%`
              : `Тест не пройден (балл: ${result.score}%). Правильные ответы не показываются — пересмотрите уроки раздела и попробуйте снова.`
          }}
        </p>
        <p v-if="submitError" class="text-sm text-red-500">{{ submitError }}</p>
        <BaseButton :disabled="!allQuestionsAnswered || submitting" @click="handleSubmit">
          Отправить тест
        </BaseButton>
      </section>
    </template>
  </div>
</template>
