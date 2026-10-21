<script setup lang="ts">
import { isAxiosError } from "axios";
import { computed, onMounted, reactive, ref } from "vue";

import { getTestInfo, startTestAttempt, submitTestAttempt } from "@/api/tests";
import SmartText from "@/components/shared/SmartText.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { AnswerPayload, Question, TestAttemptResult, TestInfo, TestKind } from "@/types";
import { pluralRu } from "@/utils/subjectTheme";

/**
 * One lesson mini-test or section test, from "start" to the result.
 *
 * The questions are not part of the lesson/section payload: each attempt is
 * started on the server, which draws that attempt's questions from the
 * test's bank. So a retake is a fresh start -- and, when the teacher gave the
 * test more questions than one attempt shows, a different set of questions.
 */
const props = defineProps<{ kind: TestKind; id: number }>();
const emit = defineEmits<{ (e: "passed"): void }>();

const info = ref<TestInfo | null>(null);
const loadError = ref("");

const attemptId = ref<number | null>(null);
const questions = ref<Question[]>([]);
const answers = reactive<Record<number, AnswerPayload>>({});
const result = ref<TestAttemptResult | null>(null);
const busy = ref(false);
const actionError = ref("");

const varies = computed(() => !!info.value && info.value.pool_size > info.value.question_count);

function errorText(e: unknown, fallback: string): string {
  // The server's own message matters: a 429 says to wait, a 403 that it is locked.
  const detail = isAxiosError(e) ? e.response?.data?.detail : null;
  return typeof detail === "string" ? detail : fallback;
}

async function loadInfo() {
  loadError.value = "";
  try {
    info.value = await getTestInfo(props.kind, props.id);
  } catch (e) {
    loadError.value = errorText(e, "Не удалось загрузить тест.");
  }
}

onMounted(loadInfo);

function resetAnswers() {
  for (const key of Object.keys(answers)) delete answers[Number(key)];
}

async function start() {
  busy.value = true;
  actionError.value = "";
  result.value = null;
  try {
    const attempt = await startTestAttempt(props.kind, props.id);
    resetAnswers();
    attemptId.value = attempt.attempt_id;
    questions.value = attempt.questions;
  } catch (e) {
    actionError.value = errorText(e, "Не удалось начать тест.");
  } finally {
    busy.value = false;
  }
}

function isAnswered(questionId: number): boolean {
  const a = answers[questionId];
  if (!a) return false;
  if (a.choice_id !== undefined) return true;
  if (a.choice_ids !== undefined) return a.choice_ids.length > 0;
  if (a.pairs !== undefined) return Object.keys(a.pairs).length > 0;
  if (a.text !== undefined) return a.text.trim().length > 0;
  return false;
}

const allAnswered = computed(() => questions.value.length > 0 && questions.value.every((q) => isAnswered(q.id)));

function setSingleChoice(questionId: number, choiceId: number) {
  answers[questionId] = { question_id: questionId, choice_id: choiceId };
}

function toggleMultipleChoice(questionId: number, choiceId: number, checked: boolean) {
  const current = answers[questionId] ?? { question_id: questionId, choice_ids: [] };
  const list = current.choice_ids ?? [];
  current.choice_ids = checked ? [...list, choiceId] : list.filter((id) => id !== choiceId);
  answers[questionId] = current;
}

function setMatchPair(questionId: number, promptId: number, answerId: string) {
  const current = answers[questionId] ?? { question_id: questionId, pairs: {} };
  current.pairs = { ...(current.pairs ?? {}), [String(promptId)]: answerId };
  answers[questionId] = current;
}

function setShortAnswer(questionId: number, text: string) {
  answers[questionId] = { question_id: questionId, text };
}

async function submit() {
  if (attemptId.value === null) return;
  busy.value = true;
  actionError.value = "";
  try {
    result.value = await submitTestAttempt(props.kind, props.id, attemptId.value, Object.values(answers));
    attemptId.value = null;
    questions.value = [];
    if (result.value.passed) emit("passed");
    await loadInfo();
  } catch (e) {
    actionError.value = errorText(e, "Не удалось отправить тест. Попробуйте ещё раз.");
  } finally {
    busy.value = false;
  }
}

function questionsLabel(n: number): string {
  return `${n} ${pluralRu(n, ["вопрос", "вопроса", "вопросов"])}`;
}
</script>

<template>
  <section class="card space-y-4 p-4">
    <p v-if="loadError" class="text-sm text-clay">{{ loadError }}</p>

    <template v-else-if="info">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-lg font-semibold text-ink">{{ kind === "lesson" ? "Мини-тест урока" : "Тест раздела" }}</h2>
        <BaseBadge :tone="info.is_passed ? 'success' : 'neutral'">
          {{ info.is_passed ? "Пройден" : "Не пройден" }}
        </BaseBadge>
      </div>

      <!-- Before an attempt (or after one): what the test is and where the student stands. -->
      <div v-if="attemptId === null" class="space-y-3">
        <p class="text-sm text-ink-2">
          {{ questionsLabel(info.question_count) }} в попытке, для зачёта нужно 50%.
          <template v-if="varies">
            В банке теста {{ questionsLabel(info.pool_size) }} — каждая новая попытка будет с другими вопросами.
          </template>
          <template v-else-if="info.question_count > 1">Порядок вопросов и вариантов меняется с каждой попыткой.</template>
        </p>
        <p v-if="info.attempts_used" class="text-sm text-ink-3">
          Попыток: {{ info.attempts_used }}<template v-if="info.best_score !== null"> · лучший результат {{ info.best_score }}%</template>
        </p>

        <p v-if="result" class="text-sm" :class="result.passed ? 'text-moss' : 'text-clay'">
          {{
            result.passed
              ? `Тест пройден, балл: ${result.score}%.`
              : `Тест не пройден (балл: ${result.score}%). Правильные ответы не показываются — повторите материал и попробуйте снова.`
          }}
        </p>

        <p v-if="!info.is_unlocked" class="text-sm text-ink-3">
          {{ kind === "lesson" ? "Урок ещё заблокирован." : "Тест откроется, когда будут пройдены все уроки раздела." }}
        </p>
        <BaseButton v-else variant="cta" :disabled="busy" @click="start">
          {{
            info.in_progress_attempt_id
              ? "Продолжить попытку"
              : info.attempts_used
                ? varies
                  ? "Пройти ещё раз — с новыми вопросами"
                  : "Пройти ещё раз"
                : "Начать тест"
          }}
        </BaseButton>
      </div>

      <!-- The attempt itself. -->
      <div v-else class="space-y-4">
        <div v-for="(question, index) in questions" :key="question.id" class="space-y-2">
          <p class="text-body-lg font-medium text-ink">
            <span class="text-ink-3">{{ index + 1 }}.</span> <SmartText :text="question.text" />
          </p>

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
                :checked="answers[question.id]?.choice_id === choice.id"
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
                :checked="(answers[question.id]?.choice_ids ?? []).includes(choice.id)"
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
                :value="answers[question.id]?.pairs?.[String(prompt.id)] ?? ''"
                @change="setMatchPair(question.id, prompt.id, ($event.target as HTMLSelectElement).value)"
              >
                <option value="" disabled>Выберите пару</option>
                <option v-for="opt in question.match_answers" :key="opt.id" :value="opt.id">{{ opt.text }}</option>
              </select>
            </div>
          </template>

          <template v-else>
            <input
              type="text"
              placeholder="Ваш ответ"
              class="input"
              :value="answers[question.id]?.text ?? ''"
              @input="setShortAnswer(question.id, ($event.target as HTMLInputElement).value)"
            />
          </template>
        </div>

        <BaseButton variant="cta" :disabled="!allAnswered || busy" @click="submit">Отправить тест</BaseButton>
      </div>

      <p v-if="actionError" class="text-sm text-clay">{{ actionError }}</p>
    </template>

    <div v-else class="h-24 animate-pulse rounded-xl bg-paper-2" />
  </section>
</template>
