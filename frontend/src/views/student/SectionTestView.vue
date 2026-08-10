<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";

import { getSectionTest, submitSectionTestAttempt } from "@/api/sections";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { AnswerPayload, SectionTest, TestAttemptResult } from "@/types";

const route = useRoute();
const sectionId = Number(route.params.id);

const test = ref<SectionTest | null>(null);
const loading = ref(true);
const loadError = ref("");

const answers = reactive<Record<number, AnswerPayload>>({});
const result = ref<TestAttemptResult | null>(null);
const submitting = ref(false);
const submitError = ref("");

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
  if (!test.value) return false;
  return test.value.questions.every((q) => isAnswered(q.id));
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
    result.value = await submitSectionTestAttempt(sectionId, Object.values(answers));
    if (result.value.passed) test.value.is_passed = true;
  } catch {
    submitError.value = "Не удалось отправить тест. Попробуйте ещё раз.";
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <PageContainer>
    <div v-if="loading" class="space-y-6">
      <div class="h-8 w-2/3 animate-pulse rounded-lg bg-paper-2"></div>
      <div class="h-64 w-full max-w-[42rem] animate-pulse rounded-2xl bg-paper-2"></div>
    </div>

    <div v-else-if="loadError" class="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-center">
      <p class="text-clay">{{ loadError }}</p>
      <BaseButton variant="secondary" @click="load">Повторить</BaseButton>
    </div>

    <template v-else-if="test">
      <PageHeader title="Тест раздела">
        <template #actions>
          <BaseBadge :tone="test.is_passed ? 'success' : 'neutral'">
            {{ test.is_passed ? "Пройден" : "Не пройден" }}
          </BaseBadge>
        </template>
      </PageHeader>

      <section class="max-w-[42rem] card space-y-4 p-4">
        <div v-for="question in test.questions" :key="question.id" class="space-y-2">
          <p class="text-body-lg font-medium text-ink">{{ question.text }}</p>

          <template v-if="question.qtype === 'single'">
            <label
              v-for="choice in question.choices"
              :key="choice.id"
              class="flex items-center gap-2 rounded-lg border border-line-strong bg-paper px-3 py-2 text-sm text-ink"
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
              class="flex items-center gap-2 rounded-lg border border-line-strong bg-paper px-3 py-2 text-sm text-ink"
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
              <span class="w-1/2 text-ink">{{ prompt.text }}</span>
              <select
                class="input w-1/2"
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
              class="input"
              @input="setShortAnswer(question.id, ($event.target as HTMLInputElement).value)"
            />
          </template>
        </div>
        <p v-if="result" class="text-sm" :class="result.passed ? 'text-moss' : 'text-clay'">
          {{
            result.passed
              ? `Тест пройден, балл: ${result.score}%`
              : `Тест не пройден (балл: ${result.score}%). Правильные ответы не показываются — пересмотрите уроки раздела и попробуйте снова.`
          }}
        </p>
        <p v-if="submitError" class="text-sm text-clay">{{ submitError }}</p>
        <BaseButton variant="cta" :disabled="!allQuestionsAnswered || submitting" @click="handleSubmit">
          Отправить тест
        </BaseButton>
      </section>
    </template>
  </PageContainer>
</template>
