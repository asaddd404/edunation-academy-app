<script setup lang="ts">
import { CheckCircle2, Clock, Coins, Trophy, XCircle } from "@lucide/vue";
import { computed, onBeforeUnmount, reactive, ref } from "vue";
import type { RouteLocationRaw } from "vue-router";

import { submitTestAttempt } from "@/api/lessons";
import SmartText from "@/components/shared/SmartText.vue";
import QuestionRenderer from "@/components/test/QuestionRenderer.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { AnswerPayload, TestAttemptResult, TestSession } from "@/types";
import { formatDuration, isAnswered } from "@/utils/answers";
import { pluralRu } from "@/utils/subjectTheme";

/**
 * A lesson mini-test or section test, end to end: start an attempt (which
 * starts the server's clock and is the only way to get the questions),
 * answer, submit once, show the result.
 *
 * The clock shown here is cosmetic -- XP is computed from the time the
 * server measured between start and submit -- but it starts from the
 * server's elapsed time, so reopening a tab mid-attempt does not appear to
 * reset it.
 */
const props = defineProps<{
  title: string;
  questionCount: number;
  isPassed: boolean;
  start: () => Promise<TestSession>;
  leaderboardTo: RouteLocationRaw;
}>();

const emit = defineEmits<{ passed: [] }>();

const phase = ref<"idle" | "starting" | "running" | "submitting" | "result">("idle");
const session = ref<TestSession | null>(null);
const answers = reactive<Record<number, AnswerPayload>>({});
const result = ref<TestAttemptResult | null>(null);
const error = ref("");

const elapsed = ref(0);
let timer: ReturnType<typeof setInterval> | null = null;

function startClock(fromSeconds: number) {
  stopClock();
  const startedAt = Date.now() - fromSeconds * 1000;
  elapsed.value = fromSeconds;
  timer = setInterval(() => (elapsed.value = Math.floor((Date.now() - startedAt) / 1000)), 1000);
}

function stopClock() {
  if (timer) clearInterval(timer);
  timer = null;
}

onBeforeUnmount(stopClock);

const answeredCount = computed(
  () => session.value?.questions.filter((q) => isAnswered(q.qtype, answers[q.id])).length ?? 0,
);
const allAnswered = computed(() => !!session.value && answeredCount.value === session.value.questions.length);

async function begin() {
  phase.value = "starting";
  error.value = "";
  result.value = null;
  for (const key of Object.keys(answers)) delete answers[Number(key)];
  try {
    session.value = await props.start();
    startClock(session.value.elapsed_seconds);
    phase.value = "running";
  } catch {
    error.value = "Не удалось начать тест. Попробуйте ещё раз.";
    phase.value = "idle";
  }
}

async function submit() {
  if (!session.value) return;
  phase.value = "submitting";
  error.value = "";
  try {
    result.value = await submitTestAttempt(session.value.attempt_id, Object.values(answers));
    stopClock();
    phase.value = "result";
    if (result.value.passed) emit("passed");
  } catch {
    error.value = "Не удалось отправить тест. Попробуйте ещё раз.";
    phase.value = "running";
  }
}
</script>

<template>
  <section class="card space-y-4 p-4 sm:p-5">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h2 class="text-lg font-medium text-ink">{{ title }}</h2>
      <span
        v-if="phase === 'running' || phase === 'submitting'"
        class="inline-flex items-center gap-1.5 rounded-full bg-paper-2 px-2.5 py-1 text-xs font-medium tabular-nums text-ink-2"
        aria-label="Время с начала попытки"
      >
        <Clock :size="14" :stroke-width="1.8" /> {{ formatDuration(elapsed) }}
      </span>
    </div>

    <!-- Not started -->
    <div v-if="phase === 'idle' || phase === 'starting'" class="space-y-3">
      <p class="text-sm text-ink-2">
        {{ questionCount }} {{ pluralRu(questionCount, ["вопрос", "вопроса", "вопросов"]) }}. Время идёт с момента старта: чем точнее и быстрее — тем больше XP.
        <template v-if="isPassed">Тест уже пройден — повторная попытка принесёт XP, только если улучшит результат.</template>
      </p>
      <p v-if="error" class="text-sm text-clay">{{ error }}</p>
      <div class="flex flex-wrap items-center gap-3">
        <BaseButton variant="cta" :disabled="phase === 'starting'" @click="begin">
          {{ isPassed ? "Пройти ещё раз" : "Начать тест" }}
        </BaseButton>
        <router-link :to="leaderboardTo" class="text-sm text-moss underline underline-offset-2 hover:opacity-70">
          Рейтинг по тесту
        </router-link>
      </div>
    </div>

    <!-- In progress -->
    <template v-else-if="(phase === 'running' || phase === 'submitting') && session">
      <ol class="space-y-6">
        <li v-for="(question, i) in session.questions" :key="question.id" class="space-y-2">
          <p class="text-body-lg font-medium text-ink">
            <span class="mr-1 text-ink-3">{{ i + 1 }}.</span><SmartText :text="question.text" />
          </p>
          <QuestionRenderer v-model="answers[question.id]" :question="question" :disabled="phase === 'submitting'" />
        </li>
      </ol>
      <p class="text-sm text-ink-2">Отвечено: {{ answeredCount }} из {{ session.questions.length }}</p>
      <p v-if="error" class="text-sm text-clay">{{ error }}</p>
      <BaseButton variant="cta" :disabled="!allAnswered || phase === 'submitting'" @click="submit">
        Отправить тест
      </BaseButton>
    </template>

    <!-- Result -->
    <div v-else-if="phase === 'result' && result" class="space-y-4 motion-safe:animate-fade-up">
      <div
        class="relative overflow-hidden rounded-2xl p-4 text-white sm:p-5"
        :class="result.passed ? 'bg-gradient-to-br from-brand-deep via-brand to-brand-deep' : 'bg-gradient-to-br from-zinc-700 to-zinc-800'"
      >
        <div
          v-if="result.passed"
          class="pointer-events-none absolute -right-10 -top-10 h-36 w-36 rounded-full bg-brand-glow/25 blur-2xl"
          aria-hidden="true"
        />
        <div class="relative flex items-center gap-4">
          <!-- Accuracy ring: the stroke length is the score. -->
          <svg viewBox="0 0 44 44" class="h-16 w-16 shrink-0 -rotate-90 sm:h-20 sm:w-20" aria-hidden="true">
            <circle cx="22" cy="22" r="18" fill="none" stroke="currentColor" stroke-width="4" class="text-white/15" />
            <circle
              cx="22"
              cy="22"
              r="18"
              fill="none"
              stroke-width="4"
              stroke-linecap="round"
              :stroke="result.passed ? '#2dd4bf' : '#f87171'"
              :stroke-dasharray="`${(result.score / 100) * 113.1} 113.1`"
              class="transition-[stroke-dasharray] duration-700"
            />
          </svg>
          <div class="min-w-0">
            <span
              class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-bold tracking-wide"
              :class="result.passed ? 'bg-green-400/20 text-green-200' : 'bg-red-400/20 text-red-200'"
            >
              <component :is="result.passed ? CheckCircle2 : XCircle" :size="12" /> {{ result.passed ? "PASS" : "FAIL" }}
            </span>
            <p class="mt-1 text-3xl font-bold tabular-nums leading-none">{{ result.score }}%</p>
            <p class="mt-1 text-xs text-white/70">Точность · попытка №{{ result.attempt_number }}</p>
          </div>
          <div v-if="result.passed" class="ml-auto text-right">
            <p class="text-[11px] uppercase tracking-wide text-white/60">Получено</p>
            <p class="text-2xl font-bold tabular-nums text-gold-light motion-safe:animate-pop-in">+{{ result.xp_earned }}</p>
            <p class="text-[11px] text-white/60">XP</p>
          </div>
        </div>
      </div>

      <dl class="grid grid-cols-3 gap-2 text-center">
        <div class="rounded-xl border border-line bg-paper-2/60 p-3">
          <dt class="flex items-center justify-center gap-1 text-xs text-ink-3"><CheckCircle2 :size="13" class="text-green-600 dark:text-green-400" /> Верно</dt>
          <dd class="mt-1 font-semibold tabular-nums text-ink">{{ result.correct_count }} из {{ result.question_count }}</dd>
        </div>
        <div class="rounded-xl border border-line bg-paper-2/60 p-3">
          <dt class="flex items-center justify-center gap-1 text-xs text-ink-3"><Coins :size="13" class="text-gold" /> XP</dt>
          <dd class="mt-1 font-semibold tabular-nums text-moss">+{{ result.xp_earned }}</dd>
        </div>
        <div class="rounded-xl border border-line bg-paper-2/60 p-3">
          <dt class="flex items-center justify-center gap-1 text-xs text-ink-3"><Clock :size="13" class="text-brand-glow" /> Время</dt>
          <dd class="mt-1 font-semibold tabular-nums text-ink">{{ formatDuration(result.duration_seconds) }}</dd>
        </div>
      </dl>

      <p v-if="result.passed && result.xp_earned === 0" class="text-xs text-ink-3">
        Результат не лучше предыдущего — XP за этот тест уже начислены.
      </p>
      <p v-else-if="result.passed" class="text-xs text-ink-3">
        {{ result.accuracy_xp }} XP за точность + {{ result.speed_bonus }} XP за скорость<template
          v-if="result.xp_earned < result.accuracy_xp + result.speed_bonus"
        >, минус уже полученные за этот тест</template>.
      </p>
      <p v-else class="text-sm text-clay">
        Нужно набрать не меньше 50%. Правильные ответы не показываются — пересмотрите материал и попробуйте снова.
      </p>

      <div class="flex flex-wrap items-center gap-3">
        <BaseButton variant="secondary" @click="begin">Пройти ещё раз</BaseButton>
        <router-link :to="leaderboardTo" class="btn-ghost inline-flex items-center gap-1.5 px-4 py-2 text-sm">
          <Trophy :size="16" :stroke-width="1.8" /> Рейтинг по тесту
        </router-link>
      </div>
    </div>
  </section>
</template>
