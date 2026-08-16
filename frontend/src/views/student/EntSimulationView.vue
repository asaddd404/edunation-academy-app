<script setup lang="ts">
import { isAxiosError } from "axios";
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";

import {
  getEntQuestionImageUrl,
  getEntSimulation,
  getEntSimulationResult,
  submitEntSimulation,
} from "@/api/ent";
import PageContainer from "@/components/layout/PageContainer.vue";
import SmartText from "@/components/shared/SmartText.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import { useExamTimer } from "@/composables/useExamTimer";
import type {
  EntQuestionStudent,
  EntSimulation,
  EntSimulationAnswerPayload,
  EntSimulationResult,
} from "@/types";
import { optionLetter, scorePercent, scoreTone } from "@/utils/examOptions";
import { capitalize } from "@/utils/subjectTheme";

const route = useRoute();
const simulationId = Number(route.params.id);

const phase = ref<"loading" | "exam" | "result" | "error">("loading");
const errorMessage = ref("");

const exam = ref<EntSimulation | null>(null);
const result = ref<EntSimulationResult | null>(null);
const answers = reactive<Record<number, EntSimulationAnswerPayload>>({});

// One question on screen at a time -- the exam is navigated through the
// number palette / arrows rather than by scrolling one long page.
const currentIndex = ref(0);
const questionCardRef = ref<HTMLElement | null>(null);

// The control bar pins directly below the app's navbar, whose height varies
// with viewport (padding + font size) -- measure it instead of guessing.
const headerOffset = ref(0);

let submitting = false;

// handleSubmit is a hoisted function declaration, so this reference is safe
// even though it's defined further down the file.
const { label: timerLabel, isCritical: timeIsCritical, start: startTimer, stop: stopTimer } =
  useExamTimer(handleSubmit);

function measureHeader() {
  headerOffset.value = document.querySelector("header")?.getBoundingClientRect().height ?? 0;
}

const questions = computed<EntQuestionStudent[]>(() => exam.value?.questions ?? []);
const currentQuestion = computed<EntQuestionStudent | null>(() => questions.value[currentIndex.value] ?? null);

function isAnswered(question: EntQuestionStudent): boolean {
  const answer = answers[question.id];
  if (!answer) return false;
  switch (question.qtype) {
    case "single":
      return answer.choice_id != null;
    case "multiple":
      return (answer.choice_ids?.length ?? 0) > 0;
    case "matching":
      return Object.keys(answer.pairs ?? {}).length > 0;
    default:
      return (answer.text ?? "").trim().length > 0;
  }
}

const answeredCount = computed(() => questions.value.filter(isAnswered).length);
const unansweredCount = computed(() => questions.value.length - answeredCount.value);
const answeredPercent = computed(() => scorePercent(answeredCount.value, questions.value.length));

interface SubjectGroup {
  subjectName: string;
  answeredCount: number;
  // {question, globalIndex} pairs, numbered 1..N within the subject rather
  // than across the whole exam -- so "Математика 1..15" and "История 1..7"
  // both start over at 1, matching how the student picked subjects at start.
  entries: { question: EntQuestionStudent; globalIndex: number }[];
}

// Grouped by first appearance rather than assumed contiguity: the backend
// currently lays questions out subject-by-subject, but grouping this way
// stays correct even if that ordering ever changes.
const subjectGroups = computed<SubjectGroup[]>(() => {
  const bySubject = new Map<string, SubjectGroup>();
  questions.value.forEach((question, globalIndex) => {
    let group = bySubject.get(question.subject_name);
    if (!group) {
      group = { subjectName: question.subject_name, answeredCount: 0, entries: [] };
      bySubject.set(question.subject_name, group);
    }
    group.entries.push({ question, globalIndex });
    if (isAnswered(question)) group.answeredCount += 1;
  });
  return [...bySubject.values()];
});

// The palette numbers questions within their subject, so the header has to
// agree -- a palette button reading "1" under a header reading "11 / 20" is
// two different answers to "where am I". Overall progress is still on screen
// as the "Отвечено" counter.
const currentPosition = computed(() => {
  for (const group of subjectGroups.value) {
    const localIndex = group.entries.findIndex((e) => e.globalIndex === currentIndex.value);
    if (localIndex !== -1) {
      return { number: localIndex + 1, total: group.entries.length };
    }
  }
  return { number: currentIndex.value + 1, total: questions.value.length };
});

// The chip grid only ever shows one subject's questions at a time -- whichever
// subject the current question belongs to -- so it stays compact instead of
// stacking every subject's numbers on top of each other.
const activeGroup = computed<SubjectGroup | null>(
  () => subjectGroups.value.find((group) => isCurrentSubject(group)) ?? null,
);

function goTo(index: number) {
  if (index < 0 || index >= questions.value.length) return;
  currentIndex.value = index;
  // Keep the question itself in view when the palette is tall on mobile.
  questionCardRef.value?.scrollIntoView({ block: "nearest" });
}

function goNext() {
  goTo(currentIndex.value + 1);
}

function jumpToSubject(group: SubjectGroup) {
  goTo(group.entries[0].globalIndex);
}

function isCurrentSubject(group: SubjectGroup): boolean {
  return group.entries.some((e) => e.globalIndex === currentIndex.value);
}

function goPrev() {
  goTo(currentIndex.value - 1);
}

function handleKeydown(event: KeyboardEvent) {
  if (phase.value !== "exam") return;
  // Don't hijack arrows while the student is editing a short answer.
  const target = event.target as HTMLElement | null;
  if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;

  if (event.key === "ArrowRight") goNext();
  else if (event.key === "ArrowLeft") goPrev();
}

async function load() {
  phase.value = "loading";
  try {
    exam.value = await getEntSimulation(simulationId);
    currentIndex.value = 0;
    phase.value = "exam";
    startTimer(exam.value.is_timed ? exam.value.remaining_seconds : null);
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

onMounted(() => {
  load();
  measureHeader();
  window.addEventListener("keydown", handleKeydown);
  window.addEventListener("resize", measureHeader);
});

onBeforeUnmount(() => {
  stopTimer();
  window.removeEventListener("keydown", handleKeydown);
  window.removeEventListener("resize", measureHeader);
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

function isChoiceSelected(questionId: number, choiceId: number): boolean {
  return answers[questionId]?.choice_id === choiceId;
}

function isChoiceChecked(questionId: number, choiceId: number): boolean {
  return (answers[questionId]?.choice_ids ?? []).includes(choiceId);
}

function selectedPair(questionId: number, promptId: number): number | "" {
  return answers[questionId]?.pairs?.[String(promptId)] ?? "";
}

async function handleSubmit() {
  if (submitting || !exam.value) return;
  submitting = true;
  stopTimer();
  try {
    result.value = await submitEntSimulation(simulationId, Object.values(answers));
    phase.value = "result";
    window.scrollTo({ top: 0 });
  } catch {
    errorMessage.value = "Не удалось отправить ответы. Попробуйте ещё раз.";
    phase.value = "error";
  } finally {
    submitting = false;
  }
}

const resultPercent = computed(() =>
  result.value ? scorePercent(result.value.total_score, result.value.max_score) : 0,
);

const RING_CIRCUMFERENCE = 2 * Math.PI * 52;
const ringDashOffset = computed(() => RING_CIRCUMFERENCE * (1 - resultPercent.value / 100));

const TONE_TEXT: Record<string, string> = {
  success: "text-green-700 dark:text-green-500",
  warning: "text-amber-700 dark:text-amber-500",
  danger: "text-red-600 dark:text-red-400",
};
const TONE_STROKE: Record<string, string> = {
  success: "stroke-green-600 dark:stroke-green-500",
  warning: "stroke-amber-600 dark:stroke-amber-500",
  danger: "stroke-red-500 dark:stroke-red-400",
};
const TONE_BAR: Record<string, string> = {
  success: "bg-green-600 dark:bg-green-500",
  warning: "bg-amber-600 dark:bg-amber-500",
  danger: "bg-red-500 dark:bg-red-400",
};

/** Per-subject totals for the result screen -- the single overall number
 * hides which subject actually cost the points. */
const resultBySubject = computed(() => {
  const bySubject = new Map<string, { name: string; score: number; max: number }>();
  for (const answer of result.value?.answers ?? []) {
    const row = bySubject.get(answer.subject_name) ?? { name: answer.subject_name, score: 0, max: 0 };
    row.score += answer.score_awarded;
    row.max += answer.max_score;
    bySubject.set(answer.subject_name, row);
  }
  return [...bySubject.values()].map((row) => {
    const percent = scorePercent(row.score, row.max);
    return { ...row, percent, tone: scoreTone(percent) };
  });
});

function timingLabel(r: EntSimulationResult): string {
  if (!r.is_timed) return "Без ограничения по времени";
  return r.time_expired ? "С таймером — время вышло" : "С таймером — уложился в срок";
}
</script>

<template>
  <PageContainer>
    <div v-if="phase === 'loading'" class="mx-auto max-w-[42rem] space-y-4">
      <div class="h-24 w-full animate-pulse rounded-2xl bg-paper-2"></div>
      <div class="h-72 w-full animate-pulse rounded-2xl bg-paper-2"></div>
    </div>

    <div v-else-if="phase === 'error'" class="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-center">
      <p class="text-clay">{{ errorMessage }}</p>
      <BaseButton variant="secondary" @click="load">Повторить</BaseButton>
    </div>

    <template v-else-if="phase === 'exam' && exam && currentQuestion">
      <!-- ── Sticky control bar: timer + question palette ──────────── -->
      <div
        class="sticky z-10 mb-5 rounded-2xl border border-line bg-paper/95 px-4 py-3 shadow-sm backdrop-blur"
        :style="{ top: `${headerOffset}px` }"
      >
        <div class="flex items-center justify-between gap-3">
          <div class="min-w-0">
            <p class="text-sm font-semibold text-ink">
              Вопрос {{ currentPosition.number }} <span class="text-ink-3">/ {{ currentPosition.total }}</span>
            </p>
            <p class="truncate text-xs text-ink-3">{{ capitalize(currentQuestion.subject_name) }}</p>
          </div>

          <div class="flex shrink-0 items-center gap-2.5">
            <div class="hidden text-right sm:block">
              <p class="text-[10px] uppercase tracking-wide text-ink-3">Отвечено</p>
              <p class="text-sm font-semibold tabular-nums text-ink">{{ answeredCount }} / {{ questions.length }}</p>
            </div>
            <div
              v-if="timerLabel"
              class="flex items-center gap-2 rounded-xl px-3 py-2 tabular-nums transition-colors duration-300"
              :class="
                timeIsCritical
                  ? 'bg-red-500/15 text-red-600 dark:text-red-400'
                  : 'bg-paper-2 text-ink'
              "
            >
              <svg class="h-4 w-4 shrink-0 opacity-70" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8">
                <circle cx="10" cy="11" r="7" />
                <path d="M10 8v3.5l2 1.5M7.5 2h5" stroke-linecap="round" />
              </svg>
              <span class="text-lg font-bold leading-none" :class="timeIsCritical ? 'animate-pulse' : ''">
                {{ timerLabel }}
              </span>
            </div>
            <BaseBadge v-else tone="neutral">Без таймера</BaseBadge>
          </div>
        </div>

        <!-- Overall progress: the palette below only covers the active
             subject, so this is the one place the whole exam is visible. -->
        <div class="mt-2.5 h-1.5 overflow-hidden rounded-full bg-paper-2">
          <div
            class="h-full rounded-full bg-moss transition-[width] duration-300 ease-out"
            :style="{ width: `${answeredPercent}%` }"
          />
        </div>

        <!-- Subject tabs: one horizontal row, active tab in solid moss.
             Skipped for single-subject exams, where it'd just repeat the
             header's subject name. -->
        <div v-if="subjectGroups.length > 1" class="mt-3 flex flex-wrap gap-2">
          <button
            v-for="group in subjectGroups"
            :key="group.subjectName"
            type="button"
            class="rounded-xl px-3 py-1.5 text-xs font-medium transition-colors duration-150"
            :class="
              isCurrentSubject(group)
                ? 'bg-moss text-moss-fg'
                : 'bg-paper-2 text-ink-2 hover:bg-line hover:text-ink'
            "
            @click="jumpToSubject(group)"
          >
            {{ capitalize(group.subjectName) }}
            <span :class="isCurrentSubject(group) ? 'text-moss-fg/80' : 'text-ink-3'">
              {{ group.answeredCount }}/{{ group.entries.length }}
            </span>
          </button>
        </div>

        <!-- Question chips: only the active subject's questions, so the grid
             never grows past one subject's worth of numbers. Capped in height
             on a phone -- 40 chips at 36px would otherwise push the question
             itself off screen -- and scrolls inside its own box. -->
        <div v-if="activeGroup" class="mt-3 flex max-h-24 flex-wrap gap-1.5 overflow-y-auto sm:max-h-none sm:overflow-visible">
          <button
            v-for="(entry, localIndex) in activeGroup.entries"
            :key="entry.question.id"
            type="button"
            class="flex h-9 w-9 items-center justify-center rounded-xl text-xs transition-colors duration-150"
            :class="
              entry.globalIndex === currentIndex
                ? 'bg-paper font-bold text-ink ring-2 ring-moss'
                : isAnswered(entry.question)
                  ? 'bg-moss font-semibold text-moss-fg'
                  : 'bg-paper-2 text-ink-3'
            "
            :aria-label="`${activeGroup.subjectName}, вопрос ${localIndex + 1}${isAnswered(entry.question) ? ', отвечен' : ''}`"
            :aria-current="entry.globalIndex === currentIndex ? 'true' : undefined"
            @click="goTo(entry.globalIndex)"
          >
            {{ localIndex + 1 }}
          </button>
        </div>
      </div>

      <div class="mx-auto max-w-[42rem] space-y-4">
        <!-- ── Current question ──────────────────────────────────────── -->
        <section ref="questionCardRef" class="card space-y-4 p-5">
          <div class="flex flex-wrap items-center gap-2 text-xs text-ink-3">
            <BaseBadge tone="neutral">{{ capitalize(currentQuestion.subject_name) }}</BaseBadge>
            <span>{{ currentQuestion.max_score }} балл(а)</span>
          </div>

          <p class="text-body-lg font-medium text-ink"><SmartText :text="currentQuestion.text" /></p>

          <img
            v-if="currentQuestion.has_image"
            :src="getEntQuestionImageUrl(currentQuestion.id)"
            alt="Изображение к вопросу"
            class="max-h-96 w-full rounded-xl border border-line object-contain"
          />

          <div class="space-y-2">
            <template v-if="currentQuestion.qtype === 'single'">
              <label
                v-for="(choice, i) in currentQuestion.choices"
                :key="choice.id"
                class="group/opt flex cursor-pointer items-center gap-3 rounded-xl border px-3.5 py-3 text-sm text-ink transition-all duration-150"
                :class="
                  isChoiceSelected(currentQuestion.id, choice.id)
                    ? 'border-moss bg-moss/10 shadow-sm'
                    : 'border-line hover:border-moss/50 hover:bg-paper-2'
                "
              >
                <!-- The native control stays in the DOM (keyboard, screen
                     readers, form semantics) but the lettered badge is what
                     the student actually sees and clicks. -->
                <input
                  type="radio"
                  class="sr-only"
                  :name="`q-${currentQuestion.id}`"
                  :value="choice.id"
                  :checked="isChoiceSelected(currentQuestion.id, choice.id)"
                  @change="setSingleChoice(currentQuestion.id, choice.id)"
                />
                <span
                  class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sm font-semibold transition-colors duration-150"
                  :class="
                    isChoiceSelected(currentQuestion.id, choice.id)
                      ? 'bg-moss text-moss-fg'
                      : 'bg-paper-2 text-ink-2 group-hover/opt:bg-line'
                  "
                >
                  {{ optionLetter(i) }}
                </span>
                <span class="flex-1">{{ choice.text }}</span>
              </label>
            </template>

            <template v-else-if="currentQuestion.qtype === 'multiple'">
              <label
                v-for="(choice, i) in currentQuestion.choices"
                :key="choice.id"
                class="group/opt flex cursor-pointer items-center gap-3 rounded-xl border px-3.5 py-3 text-sm text-ink transition-all duration-150"
                :class="
                  isChoiceChecked(currentQuestion.id, choice.id)
                    ? 'border-moss bg-moss/10 shadow-sm'
                    : 'border-line hover:border-moss/50 hover:bg-paper-2'
                "
              >
                <input
                  type="checkbox"
                  class="sr-only"
                  :checked="isChoiceChecked(currentQuestion.id, choice.id)"
                  @change="
                    toggleMultipleChoice(currentQuestion.id, choice.id, ($event.target as HTMLInputElement).checked)
                  "
                />
                <!-- Square badge, unlike the single-choice one, so "выберите
                     несколько" is readable from the shape alone. -->
                <span
                  class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border-2 text-sm font-semibold transition-colors duration-150"
                  :class="
                    isChoiceChecked(currentQuestion.id, choice.id)
                      ? 'border-moss bg-moss text-moss-fg'
                      : 'border-line-strong bg-paper text-ink-2 group-hover/opt:border-moss/50'
                  "
                >
                  {{ optionLetter(i) }}
                </span>
                <span class="flex-1">{{ choice.text }}</span>
              </label>
            </template>

            <template v-else-if="currentQuestion.qtype === 'matching'">
              <div
                v-for="(prompt, i) in currentQuestion.match_prompts"
                :key="prompt.id"
                class="flex flex-col gap-2 rounded-xl border px-3.5 py-3 text-sm transition-colors duration-150 sm:flex-row sm:items-center"
                :class="selectedPair(currentQuestion.id, prompt.id) ? 'border-moss/50 bg-moss/5' : 'border-line'"
              >
                <span class="flex flex-1 items-center gap-3">
                  <span
                    class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sm font-semibold transition-colors duration-150"
                    :class="
                      selectedPair(currentQuestion.id, prompt.id)
                        ? 'bg-moss text-moss-fg'
                        : 'bg-paper-2 text-ink-2'
                    "
                  >
                    {{ optionLetter(i) }}
                  </span>
                  <span class="text-ink">{{ prompt.text }}</span>
                </span>
                <select
                  class="input sm:w-1/2"
                  :value="selectedPair(currentQuestion.id, prompt.id)"
                  @change="setMatchPair(currentQuestion.id, prompt.id, Number(($event.target as HTMLSelectElement).value))"
                >
                  <option value="" disabled>Выберите пару</option>
                  <option v-for="opt in currentQuestion.match_answers" :key="opt.id" :value="opt.id">
                    {{ opt.text }}
                  </option>
                </select>
              </div>
            </template>

            <template v-else>
              <input
                type="text"
                placeholder="Ваш ответ"
                class="input"
                :value="answers[currentQuestion.id]?.text ?? ''"
                @input="setShortAnswer(currentQuestion.id, ($event.target as HTMLInputElement).value)"
              />
            </template>
          </div>
        </section>

        <!-- ── Navigation ────────────────────────────────────────────── -->
        <div class="flex items-center justify-between gap-3">
          <BaseButton variant="secondary" :disabled="currentIndex === 0" @click="goPrev">← Назад</BaseButton>
          <!-- Keyboard hint only where there is a keyboard to use it. -->
          <span class="hidden text-xs text-ink-3 sm:inline">← → для перехода</span>
          <BaseButton
            variant="secondary"
            :disabled="currentIndex === questions.length - 1"
            @click="goNext"
          >
            Вперёд →
          </BaseButton>
        </div>

        <div class="card p-5">
          <p v-if="unansweredCount > 0" class="mb-3 text-sm text-ink-2">
            Без ответа осталось: <span class="font-medium text-ink">{{ unansweredCount }}</span>. Непройденные вопросы
            отмечены в списке сверху.
          </p>
          <p v-else class="mb-3 text-sm text-moss">Все вопросы отвечены.</p>

          <p v-if="errorMessage" class="mb-3 text-sm text-clay">{{ errorMessage }}</p>
          <BaseButton variant="cta" class="w-full sm:w-auto" :disabled="submitting" @click="handleSubmit">
            Завершить и сдать
          </BaseButton>
        </div>
      </div>
    </template>

    <div v-else-if="phase === 'exam'" class="card mx-auto flex max-w-[42rem] flex-col items-center gap-3 px-6 py-12 text-center">
      <span class="flex h-14 w-14 items-center justify-center rounded-full bg-paper-2 text-ink-3">
        <svg class="h-7 w-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
          <path d="M4 7h6l2 2h8v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7Z" stroke-linejoin="round" />
        </svg>
      </span>
      <p class="font-medium text-ink">В этой попытке не осталось вопросов</p>
      <p class="max-w-xs text-sm text-ink-2">
        Похоже, вопросы для этой симуляции были удалены после её начала. Начните новую попытку в ЕНТ-тренажёре.
      </p>
      <router-link to="/ent" class="btn-primary">К ЕНТ-тренажёру</router-link>
    </div>

    <template v-else-if="phase === 'result' && result">
      <div class="mx-auto max-w-[42rem] space-y-6">
        <section class="card overflow-hidden">
          <div class="flex flex-col items-center gap-5 p-6 text-center sm:flex-row sm:text-left">
            <div class="relative h-32 w-32 shrink-0">
              <svg class="h-full w-full -rotate-90" viewBox="0 0 120 120">
                <circle cx="60" cy="60" r="52" fill="none" stroke-width="10" class="stroke-paper-2" />
                <circle
                  cx="60"
                  cy="60"
                  r="52"
                  fill="none"
                  stroke-width="10"
                  stroke-linecap="round"
                  :class="TONE_STROKE[scoreTone(resultPercent)]"
                  :stroke-dasharray="RING_CIRCUMFERENCE"
                  :stroke-dashoffset="ringDashOffset"
                  style="transition: stroke-dashoffset 900ms cubic-bezier(0.16, 1, 0.3, 1)"
                />
              </svg>
              <div class="absolute inset-0 flex flex-col items-center justify-center">
                <span class="text-3xl font-bold tabular-nums" :class="TONE_TEXT[scoreTone(resultPercent)]">
                  {{ resultPercent }}%
                </span>
                <span class="text-xs text-ink-3">{{ result.total_score }} / {{ result.max_score }}</span>
              </div>
            </div>

            <div class="min-w-0 flex-1">
              <h1 class="font-display text-display-sm text-ink">Результат</h1>
              <div class="mt-2 flex flex-wrap items-center justify-center gap-2 sm:justify-start">
                <span class="rounded-full bg-moss px-3 py-1 text-sm font-semibold text-moss-fg">
                  +{{ result.xp_earned }} XP
                </span>
                <BaseBadge :tone="result.time_expired ? 'danger' : 'neutral'">{{ timingLabel(result) }}</BaseBadge>
              </div>
              <div class="mt-4 flex flex-wrap justify-center gap-2 sm:justify-start">
                <router-link to="/ent" class="btn-primary px-4 py-2 text-sm">Пройти ещё раз</router-link>
                <router-link to="/ent/leaderboard" class="btn-ghost px-4 py-2 text-sm">Рейтинг</router-link>
              </div>
            </div>
          </div>

          <div v-if="resultBySubject.length > 1" class="border-t border-line px-6 py-4">
            <p class="mb-3 text-xs uppercase tracking-wide text-ink-3">По предметам</p>
            <div class="space-y-2.5">
              <div v-for="row in resultBySubject" :key="row.name" class="flex items-center gap-3 text-sm">
                <span class="w-28 shrink-0 truncate text-ink-2 sm:w-40">{{ capitalize(row.name) }}</span>
                <div class="h-2 flex-1 overflow-hidden rounded-full bg-paper-2">
                  <div
                    class="h-full rounded-full transition-[width] duration-700 ease-out"
                    :class="TONE_BAR[row.tone]"
                    :style="{ width: `${row.percent}%` }"
                  />
                </div>
                <span class="w-14 shrink-0 text-right tabular-nums text-ink">{{ row.score }}/{{ row.max }}</span>
              </div>
            </div>
          </div>
        </section>

        <p class="text-sm font-medium text-ink">Разбор ответов</p>

        <section
          v-for="answer in result.answers"
          :key="answer.question_id"
          class="card space-y-2 border-l-[3px] p-4"
          :class="
            answer.is_correct
              ? 'border-l-green-600 dark:border-l-green-500'
              : answer.score_awarded > 0
                ? 'border-l-amber-600 dark:border-l-amber-500'
                : 'border-l-red-500 dark:border-l-red-400'
          "
        >
          <div class="flex items-center gap-2 text-xs text-ink-3">
            <BaseBadge tone="neutral">{{ capitalize(answer.subject_name) }}</BaseBadge>
            <BaseBadge :tone="answer.is_correct ? 'success' : answer.score_awarded > 0 ? 'warning' : 'danger'">
              {{ answer.score_awarded }} / {{ answer.max_score }}
            </BaseBadge>
          </div>
          <p class="text-body-lg font-medium text-ink"><SmartText :text="answer.text" /></p>

          <img
            v-if="answer.has_image"
            :src="getEntQuestionImageUrl(answer.question_id)"
            alt="Изображение к вопросу"
            class="max-h-72 w-full rounded-xl border border-line object-contain"
          />

          <ul v-if="answer.choices.length" class="space-y-1.5 text-sm">
            <li
              v-for="(choice, i) in answer.choices"
              :key="choice.id"
              class="flex items-center gap-2.5 rounded-lg px-2 py-1.5"
              :class="choice.is_correct ? 'bg-green-600/10' : ''"
            >
              <span
                class="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs font-semibold"
                :class="
                  choice.is_correct
                    ? 'bg-green-600 text-white dark:bg-green-500 dark:text-zinc-900'
                    : 'bg-paper-2 text-ink-3'
                "
              >
                {{ optionLetter(i) }}
              </span>
              <span :class="choice.is_correct ? 'font-medium text-ink' : 'text-ink-2'">{{ choice.text }}</span>
            </li>
          </ul>

          <ul v-else-if="answer.match_pairs.length" class="space-y-1 text-sm">
            <li v-for="pair in answer.match_pairs" :key="pair.id" class="text-ink-2">
              {{ pair.prompt_text }} → {{ pair.answer_text }}
            </li>
          </ul>

          <ul v-else-if="answer.answer_variants.length" class="space-y-1 text-sm text-ink-2">
            <li>Верный ответ: {{ answer.answer_variants.map((v) => v.text).join(", ") }}</li>
          </ul>
        </section>
      </div>
    </template>
  </PageContainer>
</template>
