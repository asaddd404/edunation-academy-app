<script setup lang="ts">
import { isAxiosError } from "axios";
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";

import { getEntSimulation, getEntSimulationResult, submitEntSimulation } from "@/api/ent";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { EntSimulation, EntSimulationAnswerPayload, EntSimulationResult } from "@/types";

const route = useRoute();
const simulationId = Number(route.params.id);

const phase = ref<"loading" | "exam" | "result" | "error">("loading");
const errorMessage = ref("");

const exam = ref<EntSimulation | null>(null);
const result = ref<EntSimulationResult | null>(null);
const answers = reactive<Record<number, EntSimulationAnswerPayload>>({});

const remainingSeconds = ref<number | null>(null);
let timerHandle: number | undefined;
let submitting = false;

const timerLabel = computed(() => {
  if (remainingSeconds.value === null) return null;
  const m = Math.floor(remainingSeconds.value / 60);
  const s = remainingSeconds.value % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
});

function stopTimer() {
  if (timerHandle !== undefined) {
    clearInterval(timerHandle);
    timerHandle = undefined;
  }
}

function startTimer() {
  stopTimer();
  if (remainingSeconds.value === null) return;
  timerHandle = window.setInterval(() => {
    if (remainingSeconds.value === null) return;
    remainingSeconds.value -= 1;
    if (remainingSeconds.value <= 0) {
      remainingSeconds.value = 0;
      stopTimer();
      handleSubmit();
    }
  }, 1000);
}

async function load() {
  phase.value = "loading";
  try {
    exam.value = await getEntSimulation(simulationId);
    remainingSeconds.value = exam.value.remaining_seconds;
    phase.value = "exam";
    if (exam.value.is_timed) startTimer();
  } catch (e) {
    if (isAxiosError(e) && e.response?.status === 409) {
      try {
        result.value = await getEntSimulationResult(simulationId);
        phase.value = "result";
        return;
      } catch {
        // fall through to error
      }
    }
    errorMessage.value = "Не удалось загрузить симуляцию.";
    phase.value = "error";
  }
}

onMounted(load);
onBeforeUnmount(stopTimer);

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

async function handleSubmit() {
  if (submitting || !exam.value) return;
  submitting = true;
  stopTimer();
  try {
    result.value = await submitEntSimulation(simulationId, Object.values(answers));
    phase.value = "result";
  } catch {
    errorMessage.value = "Не удалось отправить ответы. Попробуйте ещё раз.";
    phase.value = "error";
  } finally {
    submitting = false;
  }
}

function timingLabel(r: EntSimulationResult): string {
  if (!r.is_timed) return "Без ограничения по времени";
  return r.time_expired ? "С таймером — время вышло" : "С таймером — уложился в срок";
}
</script>

<template>
  <div class="mx-auto max-w-2xl space-y-6">
    <p v-if="phase === 'loading'" class="text-fg/60">Загрузка…</p>
    <p v-else-if="phase === 'error'" class="text-red-600 dark:text-red-500">{{ errorMessage }}</p>

    <template v-else-if="phase === 'exam' && exam">
      <div class="flex items-center justify-between">
        <h1 class="text-2xl font-semibold">ЕНТ-симуляция</h1>
        <BaseBadge v-if="timerLabel" :tone="remainingSeconds && remainingSeconds < 60 ? 'danger' : 'neutral'">
          Осталось: {{ timerLabel }}
        </BaseBadge>
        <BaseBadge v-else tone="neutral">Без ограничения по времени</BaseBadge>
      </div>

      <section v-for="question in exam.questions" :key="question.id" class="space-y-2 rounded-2xl border border-border bg-card p-4 transition-all duration-200">
        <div class="flex items-center gap-2 text-xs text-fg/50">
          <BaseBadge tone="neutral">{{ question.subject_name }}</BaseBadge>
          <span>{{ question.max_score }} балл(а)</span>
        </div>
        <p class="font-medium">{{ question.text }}</p>

        <template v-if="question.qtype === 'single'">
          <label
            v-for="choice in question.choices"
            :key="choice.id"
            class="flex items-center gap-2 rounded-lg border border-fg/10 px-3 py-2 text-sm"
          >
            <input
              type="radio"
              :name="`q-${question.id}`"
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
      </section>

      <p v-if="errorMessage" class="text-sm text-red-600 dark:text-red-500">{{ errorMessage }}</p>
      <BaseButton variant="cta" :disabled="submitting" @click="handleSubmit">Завершить и сдать</BaseButton>
    </template>

    <template v-else-if="phase === 'result' && result">
      <div>
        <h1 class="mb-2 text-2xl font-semibold">Результат</h1>
        <div class="flex flex-wrap items-center gap-2">
          <BaseBadge tone="success">{{ result.total_score }} / {{ result.max_score }} баллов</BaseBadge>
          <BaseBadge :tone="result.time_expired ? 'danger' : 'neutral'">{{ timingLabel(result) }}</BaseBadge>
          <span class="rounded-full bg-pop px-2.5 py-1 text-xs font-semibold text-black">+{{ result.xp_earned }} XP</span>
        </div>
        <router-link class="mt-2 inline-block text-sm text-accent underline underline-offset-2 hover:opacity-70" to="/ent/leaderboard">
          Смотреть рейтинг
        </router-link>
      </div>

      <section
        v-for="answer in result.answers"
        :key="answer.question_id"
        class="space-y-2 rounded-2xl border border-border bg-card p-4 transition-all duration-200"
      >
        <div class="flex items-center gap-2 text-xs text-fg/50">
          <BaseBadge tone="neutral">{{ answer.subject_name }}</BaseBadge>
          <BaseBadge :tone="answer.is_correct ? 'success' : answer.score_awarded > 0 ? 'warning' : 'danger'">
            {{ answer.score_awarded }} / {{ answer.max_score }}
          </BaseBadge>
        </div>
        <p class="font-medium">{{ answer.text }}</p>

        <ul v-if="answer.choices.length" class="space-y-1 text-sm">
          <li
            v-for="choice in answer.choices"
            :key="choice.id"
            :class="choice.is_correct ? 'text-green-700 dark:text-green-500' : 'text-fg/70'"
          >
            {{ choice.is_correct ? "✓" : "·" }} {{ choice.text }}
          </li>
        </ul>

        <ul v-else-if="answer.match_pairs.length" class="space-y-1 text-sm">
          <li v-for="pair in answer.match_pairs" :key="pair.id" class="text-fg/70">
            {{ pair.prompt_text }} → {{ pair.answer_text }}
          </li>
        </ul>

        <ul v-else-if="answer.answer_variants.length" class="space-y-1 text-sm text-fg/70">
          <li>Верный ответ: {{ answer.answer_variants.map((v) => v.text).join(", ") }}</li>
        </ul>
      </section>
    </template>
  </div>
</template>
