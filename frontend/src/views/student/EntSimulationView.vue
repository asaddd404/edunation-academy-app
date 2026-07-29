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
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type {
  EntQuestionStudent,
  EntSimulation,
  EntSimulationAnswerPayload,
  EntSimulationResult,
} from "@/types";
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

const remainingSeconds = ref<number | null>(null);
let timerHandle: number | undefined;
let submitting = false;

function measureHeader() {
  headerOffset.value = document.querySelector("header")?.getBoundingClientRect().height ?? 0;
}

const questions = computed<EntQuestionStudent[]>(() => exam.value?.questions ?? []);
const currentQuestion = computed<EntQuestionStudent | null>(() => questions.value[currentIndex.value] ?? null);

const timerLabel = computed(() => {
  if (remainingSeconds.value === null) return null;
  const total = remainingSeconds.value;
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = h > 0 ? m.toString().padStart(2, "0") : m.toString();
  return `${h > 0 ? `${h}:` : ""}${mm}:${s.toString().padStart(2, "0")}`;
});

const timeIsCritical = computed(() => remainingSeconds.value !== null && remainingSeconds.value <= 60);

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

function goTo(index: number) {
  if (index < 0 || index >= questions.value.length) return;
  currentIndex.value = index;
  // Keep the question itself in view when the palette is tall on mobile.
  questionCardRef.value?.scrollIntoView({ block: "nearest" });
}

function goNext() {
  goTo(currentIndex.value + 1);
}

// Jumping to a subject lands on its first unanswered question -- picking up
// where the student left off -- or its first question once every question
// in that subject is already answered.
function jumpToSubject(group: SubjectGroup) {
  const target = group.entries.find((e) => !isAnswered(e.question)) ?? group.entries[0];
  goTo(target.globalIndex);
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
    currentIndex.value = 0;
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

function timingLabel(r: EntSimulationResult): string {
  if (!r.is_timed) return "Без ограничения по времени";
  return r.time_expired ? "С таймером — время вышло" : "С таймером — уложился в срок";
}
</script>

<template>
  <div class="mx-auto max-w-3xl">
    <p v-if="phase === 'loading'" class="text-fg/60">Загрузка…</p>
    <p v-else-if="phase === 'error'" class="text-red-600 dark:text-red-500">{{ errorMessage }}</p>

    <template v-else-if="phase === 'exam' && exam && currentQuestion">
      <!-- ── Sticky control bar: timer + question palette ──────────── -->
      <div
        class="sticky z-10 -mx-4 mb-5 border-b border-border bg-bg/95 px-4 py-3 backdrop-blur"
        :style="{ top: `${headerOffset}px` }"
      >
        <div class="flex items-center justify-between gap-3">
          <div class="min-w-0">
            <p class="text-sm font-semibold">
              Вопрос {{ currentIndex + 1 }} <span class="text-fg/40">/ {{ questions.length }}</span>
            </p>
            <p class="truncate text-xs text-fg/50">{{ currentQuestion.subject_name }}</p>
          </div>

          <div class="flex shrink-0 items-center gap-3">
            <div class="text-right">
              <p class="text-xs text-fg/50">Отвечено</p>
              <p class="text-sm font-medium">{{ answeredCount }} / {{ questions.length }}</p>
            </div>
            <div
              v-if="timerLabel"
              class="rounded-xl px-3 py-2 text-center tabular-nums transition-colors duration-300"
              :class="timeIsCritical ? 'bg-red-500/15 text-red-600 dark:text-red-400' : 'bg-fg/5 text-fg'"
            >
              <p class="text-[10px] uppercase tracking-wide opacity-60">Осталось</p>
              <p class="text-lg font-bold leading-none">{{ timerLabel }}</p>
            </div>
            <BaseBadge v-else tone="neutral">Без таймера</BaseBadge>
          </div>
        </div>

        <!-- 35 numbers eat a lot of sticky height on a phone -- let the grid
             scroll instead of pushing the question off screen. -->
        <div class="mt-3 max-h-[8.5rem] space-y-2 overflow-y-auto sm:max-h-none">
          <div v-for="group in subjectGroups" :key="group.subjectName">
            <!-- Only worth a label once there's more than one subject to tell
                 apart -- a single-subject exam just numbers straight through. -->
            <button
              v-if="subjectGroups.length > 1"
              type="button"
              class="mb-1 flex items-center gap-1.5 text-xs font-medium transition-colors duration-150"
              :class="isCurrentSubject(group) ? 'text-fg' : 'text-fg/50 hover:text-fg'"
              @click="jumpToSubject(group)"
            >
              {{ capitalize(group.subjectName) }}
              <span class="text-fg/40">{{ group.answeredCount }}/{{ group.entries.length }}</span>
            </button>
            <div class="flex flex-wrap gap-1.5">
              <button
                v-for="(entry, localIndex) in group.entries"
                :key="entry.question.id"
                type="button"
                class="h-8 w-8 rounded-lg border text-xs font-medium transition-all duration-150"
                :class="
                  entry.globalIndex === currentIndex
                    ? 'border-transparent bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-500/25'
                    : isAnswered(entry.question)
                      ? 'border-transparent bg-emerald-500/20 text-emerald-700 hover:bg-emerald-500/30 dark:text-emerald-400'
                      : 'border-border text-fg/50 hover:border-indigo-500/40 hover:text-fg'
                "
                :aria-label="`${group.subjectName}, вопрос ${localIndex + 1}${isAnswered(entry.question) ? ', отвечен' : ''}`"
                :aria-current="entry.globalIndex === currentIndex ? 'true' : undefined"
                @click="goTo(entry.globalIndex)"
              >
                {{ localIndex + 1 }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- ── Current question ──────────────────────────────────────── -->
      <section ref="questionCardRef" class="space-y-4 rounded-2xl border border-border bg-card p-5">
        <div class="flex flex-wrap items-center gap-2 text-xs text-fg/50">
          <BaseBadge tone="neutral">{{ currentQuestion.subject_name }}</BaseBadge>
          <span>{{ currentQuestion.max_score }} балл(а)</span>
        </div>

        <p class="text-base font-medium">{{ currentQuestion.text }}</p>

        <img
          v-if="currentQuestion.has_image"
          :src="getEntQuestionImageUrl(currentQuestion.id)"
          alt="Изображение к вопросу"
          class="max-h-96 w-full rounded-xl border border-border object-contain"
        />

        <div class="space-y-2">
          <template v-if="currentQuestion.qtype === 'single'">
            <label
              v-for="choice in currentQuestion.choices"
              :key="choice.id"
              class="flex cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 text-sm transition-colors duration-150"
              :class="
                isChoiceSelected(currentQuestion.id, choice.id)
                  ? 'border-indigo-500 bg-indigo-500/10'
                  : 'border-fg/10 hover:border-fg/25'
              "
            >
              <input
                type="radio"
                :name="`q-${currentQuestion.id}`"
                :value="choice.id"
                :checked="isChoiceSelected(currentQuestion.id, choice.id)"
                @change="setSingleChoice(currentQuestion.id, choice.id)"
              />
              {{ choice.text }}
            </label>
          </template>

          <template v-else-if="currentQuestion.qtype === 'multiple'">
            <label
              v-for="choice in currentQuestion.choices"
              :key="choice.id"
              class="flex cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 text-sm transition-colors duration-150"
              :class="
                isChoiceChecked(currentQuestion.id, choice.id)
                  ? 'border-indigo-500 bg-indigo-500/10'
                  : 'border-fg/10 hover:border-fg/25'
              "
            >
              <input
                type="checkbox"
                :checked="isChoiceChecked(currentQuestion.id, choice.id)"
                @change="
                  toggleMultipleChoice(currentQuestion.id, choice.id, ($event.target as HTMLInputElement).checked)
                "
              />
              {{ choice.text }}
            </label>
          </template>

          <template v-else-if="currentQuestion.qtype === 'matching'">
            <div
              v-for="prompt in currentQuestion.match_prompts"
              :key="prompt.id"
              class="flex flex-col gap-2 rounded-xl border border-fg/10 px-4 py-3 text-sm sm:flex-row sm:items-center"
            >
              <span class="sm:w-1/2">{{ prompt.text }}</span>
              <select
                class="rounded-lg border border-fg/20 bg-transparent px-3 py-2 sm:w-1/2"
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
              class="w-full rounded-xl border border-fg/20 bg-transparent px-4 py-3 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
              :value="answers[currentQuestion.id]?.text ?? ''"
              @input="setShortAnswer(currentQuestion.id, ($event.target as HTMLInputElement).value)"
            />
          </template>
        </div>
      </section>

      <!-- ── Navigation ────────────────────────────────────────────── -->
      <div class="mt-4 flex items-center justify-between gap-3">
        <BaseButton variant="secondary" :disabled="currentIndex === 0" @click="goPrev">← Назад</BaseButton>
        <span class="text-xs text-fg/40">← → для перехода</span>
        <BaseButton
          variant="secondary"
          :disabled="currentIndex === questions.length - 1"
          @click="goNext"
        >
          Вперёд →
        </BaseButton>
      </div>

      <div class="mt-6 rounded-2xl border border-border bg-card p-5">
        <p v-if="unansweredCount > 0" class="mb-3 text-sm text-fg/60">
          Без ответа осталось: <span class="font-medium text-fg">{{ unansweredCount }}</span>. Непройденные вопросы
          отмечены серым в списке сверху.
        </p>
        <p v-else class="mb-3 text-sm text-emerald-600 dark:text-emerald-400">Все вопросы отвечены.</p>

        <p v-if="errorMessage" class="mb-3 text-sm text-red-600 dark:text-red-500">{{ errorMessage }}</p>
        <BaseButton variant="cta" class="w-full sm:w-auto" :disabled="submitting" @click="handleSubmit">
          Завершить и сдать
        </BaseButton>
      </div>
    </template>

    <template v-else-if="phase === 'result' && result">
      <div class="space-y-6">
        <div>
          <h1 class="mb-2 text-2xl font-semibold">Результат</h1>
          <div class="flex flex-wrap items-center gap-2">
            <BaseBadge tone="success">{{ result.total_score }} / {{ result.max_score }} баллов</BaseBadge>
            <BaseBadge :tone="result.time_expired ? 'danger' : 'neutral'">{{ timingLabel(result) }}</BaseBadge>
            <span class="rounded-full bg-pop px-2.5 py-1 text-xs font-semibold text-black">+{{ result.xp_earned }} XP</span>
          </div>
          <router-link
            class="mt-2 inline-block text-sm text-accent underline underline-offset-2 hover:opacity-70"
            to="/ent/leaderboard"
          >
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

          <img
            v-if="answer.has_image"
            :src="getEntQuestionImageUrl(answer.question_id)"
            alt="Изображение к вопросу"
            class="max-h-72 w-full rounded-xl border border-border object-contain"
          />

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
      </div>
    </template>
  </div>
</template>
