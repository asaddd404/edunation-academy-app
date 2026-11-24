<script setup lang="ts">
import { isAxiosError } from "axios";
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";

import {
  getHomeworkState,
  practiceHomework,
  saveHomeworkAnswers,
  startHomework,
  submitHomeworkAttempt,
  uploadHomeworkFile,
} from "@/api/autoHomework";
import HwAnswerTask from "@/components/autohw/HwAnswerTask.vue";
import HwReviewTask from "@/components/autohw/HwReviewTask.vue";
import type { HwAnswer, HwAnswers, HwAttempt, HwReviewBlock, HwState } from "@/types/autoHomework";
import { describeApiError } from "@/utils/apiError";
import { clockLeft, formatKz, formatPoints, humanLeft, isAnswered } from "@/utils/hwTasks";

/**
 * The auto-checked homework on a student's lesson page: what's due and
 * when, the attempt itself, the result, and -- once the key opens -- the
 * review and «Работа над ошибками».
 *
 * During an attempt answers are saved as the student goes (a moment after
 * each change, and every 20 s), so a closed tab, a dead battery or a timer
 * running out loses nothing that was typed in time.
 */
const props = defineProps<{ lessonId: number; title?: string }>();

const state = ref<HwState | null>(null);
const loadError = ref<string | null>(null);
const mode = ref<"overview" | "running" | "practice">("overview");
const attempt = ref<HwAttempt | null>(null);
const answers = reactive<HwAnswers>({});
const notice = ref<string | null>(null);
const actionError = ref<string | null>(null);
const busy = ref(false);
const root = ref<HTMLElement | null>(null);

// Clock: the server's time is the truth; the device clock may be off.
const now = ref(Date.now());
let skew = 0;
let tick: ReturnType<typeof setInterval> | null = null;

function syncClock(serverNow: string | undefined) {
  if (serverNow) skew = new Date(serverNow).getTime() - Date.now();
}
const serverNow = computed(() => now.value + skew);

async function load() {
  loadError.value = null;
  try {
    state.value = await getHomeworkState(props.lessonId);
    syncClock(state.value.server_now);
  } catch (e) {
    // 403: the lesson is locked -- the page above already says so.
    if (isAxiosError(e) && e.response?.status === 403) state.value = null;
    else loadError.value = describeApiError(e, "Не удалось загрузить домашку.");
  }
}

onMounted(async () => {
  await load();
  tick = setInterval(() => (now.value = Date.now()), 1000);
});

// ── overview ─────────────────────────────────────────────────────────────

const s = computed(() => state.value);
const deadlineLeft = computed(() => (s.value?.deadline ? new Date(s.value.deadline).getTime() - serverNow.value : null));
const opensLeft = computed(() => (s.value?.opens_at ? new Date(s.value.opens_at).getTime() - serverNow.value : null));

const startLabel = computed(() => {
  if (!s.value) return "";
  if (s.value.open_attempt) return "Продолжить";
  if (s.value.attempts_used > 0) return s.value.attempts_left == null ? "Решить ещё раз" : `Решить ещё раз (осталось ${s.value.attempts_left})`;
  return "Начать";
});

const attemptsLine = computed(() => {
  if (!s.value) return "";
  if (s.value.max_attempts == null) return `Попыток: без ограничений (использовано ${s.value.attempts_used})`;
  return `Попытки: ${s.value.attempts_used} из ${s.value.max_attempts}`;
});

const revealLine = computed(() => {
  const st = s.value;
  if (!st?.result || st.reveal) return null;
  if (st.reveal_at) return `Какие задания неверны и правильные ответы вы увидите после срока сдачи — ${formatKz(st.reveal_at)}.`;
  return "Какие задания неверны и правильные ответы вы увидите, когда используете все попытки или решите всё верно.";
});

// ── attempt ──────────────────────────────────────────────────────────────

const awayCount = ref(0);
const saveState = ref<"saved" | "saving" | "dirty" | "error">("saved");
const savedAt = ref<number | null>(null);
const uploading = reactive<Record<number, boolean>>({});
const confirmSubmit = ref(false);
let saveTimer: ReturnType<typeof setTimeout> | null = null;
let periodic: ReturnType<typeof setInterval> | null = null;
let inFlight = false;
let again = false;
let submitting = false;

function fillAnswers(a: HwAttempt) {
  for (const key of Object.keys(answers)) delete answers[key];
  for (const task of a.tasks) {
    const stored = a.answers[String(task.id)];
    const copy: HwAnswer = stored ? JSON.parse(JSON.stringify(stored)) : {};
    // The list as shown is a valid first answer: untouched still counts
    // whatever already stands in the right place.
    if (task.type === "order" && !copy.order?.length) copy.order = (task.items ?? []).map((i) => i.id);
    answers[String(task.id)] = copy;
  }
}

async function start() {
  busy.value = true;
  actionError.value = null;
  notice.value = null;
  try {
    const a = await startHomework(props.lessonId);
    syncClock(a.server_now);
    attempt.value = a;
    fillAnswers(a);
    awayCount.value = 0;
    saveState.value = "saved";
    mode.value = "running";
    periodic = setInterval(() => {
      if (saveState.value === "dirty") void save();
    }, 20_000);
    root.value?.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    actionError.value = describeApiError(e, "Не удалось начать.");
    await load();
  } finally {
    busy.value = false;
  }
}

watch(
  answers,
  () => {
    if (mode.value !== "running") return;
    saveState.value = "dirty";
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => void save(), 1500);
  },
  { deep: true },
);

function payload(): HwAnswers {
  const out: HwAnswers = {};
  for (const [k, v] of Object.entries(answers)) if (!("file_name" in v)) out[k] = v;
  return out;
}

async function save() {
  if (!attempt.value || mode.value !== "running") return;
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = null;
  if (inFlight) {
    again = true;
    return;
  }
  inFlight = true;
  saveState.value = "saving";
  try {
    const r = await saveHomeworkAnswers(attempt.value.id, payload(), awayCount.value);
    syncClock(r.server_now);
    if (attempt.value) attempt.value.expires_at = r.expires_at; // the teacher may have added time
    saveState.value = "saved";
    savedAt.value = Date.now();
  } catch (e) {
    if (isAxiosError(e) && e.response?.status === 409) {
      // Time ran out or the attempt was closed elsewhere: show where things stand.
      finishRunning(describeApiError(e));
      await load();
      return;
    }
    saveState.value = "error";
  } finally {
    inFlight = false;
    if (again) {
      again = false;
      void save();
    }
  }
}

const expiresAt = computed(() => (attempt.value?.expires_at ? new Date(attempt.value.expires_at).getTime() : null));
const timeLeft = computed(() => (expiresAt.value == null ? null : expiresAt.value - serverNow.value));
// A ticking clock is for a timed attempt or the last hours before the
// deadline; "37:35:04" for a deadline two days away just looks broken.
const showClock = computed(() => timeLeft.value != null && (!!state.value?.time_limit_minutes || timeLeft.value < 3 * 3600_000));

watch(timeLeft, (left) => {
  if (left != null && left <= 0 && mode.value === "running" && !submitting) void submit(true);
});

const unanswered = computed(() => (attempt.value?.tasks ?? []).filter((t) => !isAnswered(t.type, answers[String(t.id)])).length);

async function submit(auto = false) {
  if (!attempt.value || submitting) return;
  if (!auto && unanswered.value > 0 && !confirmSubmit.value) {
    confirmSubmit.value = true;
    return;
  }
  submitting = true;
  busy.value = true;
  actionError.value = null;
  try {
    const result = await submitHomeworkAttempt(attempt.value.id, payload(), awayCount.value);
    state.value = result;
    syncClock(result.server_now);
    finishRunning(
      result.late
        ? "Время вышло — засчитаны ответы, сохранённые вовремя."
        : auto
          ? "Время вышло — ответы отправлены автоматически."
          : "Ответы отправлены.",
    );
  } catch (e) {
    if (isAxiosError(e) && e.response?.status === 409) {
      finishRunning(describeApiError(e));
      await load();
    } else {
      actionError.value = describeApiError(e, "Не удалось отправить. Ответы сохранены — попробуйте ещё раз.");
    }
  } finally {
    submitting = false;
    busy.value = false;
  }
}

function finishRunning(message: string | null) {
  mode.value = "overview";
  attempt.value = null;
  confirmSubmit.value = false;
  if (saveTimer) clearTimeout(saveTimer);
  if (periodic) clearInterval(periodic);
  saveTimer = null;
  periodic = null;
  notice.value = message;
  root.value?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function upload(taskId: number, file: File) {
  if (!attempt.value) return;
  uploading[taskId] = true;
  actionError.value = null;
  try {
    const r = await uploadHomeworkFile(attempt.value.id, taskId, file);
    answers[String(taskId)] = { file_name: r.file_name };
  } catch (e) {
    actionError.value = describeApiError(e, "Не удалось загрузить файл.");
  } finally {
    uploading[taskId] = false;
  }
}

// Leaving the page during an attempt: a hint for the teacher (never a
// penalty), and a chance to save what's typed.
function onVisibility() {
  if (mode.value !== "running") return;
  if (document.hidden) {
    awayCount.value += 1;
    void save();
  }
}
function onBeforeUnload(e: BeforeUnloadEvent) {
  if (mode.value === "running" && saveState.value !== "saved") {
    void save();
    e.preventDefault();
  }
}
document.addEventListener("visibilitychange", onVisibility);
window.addEventListener("beforeunload", onBeforeUnload);

onBeforeUnmount(() => {
  document.removeEventListener("visibilitychange", onVisibility);
  window.removeEventListener("beforeunload", onBeforeUnload);
  if (tick) clearInterval(tick);
  if (periodic) clearInterval(periodic);
  if (saveTimer) {
    clearTimeout(saveTimer);
    void save();
  }
});

// ── practice («Работа над ошибками») ───────────────────────────────────────

const wrongBlocks = computed<HwReviewBlock[]>(() =>
  (s.value?.review ?? []).filter((b) => b.task.type !== "essay" && b.task.type !== "file" && (b.earned ?? 0) < b.max - 1e-9),
);
const practiceAnswers = reactive<HwAnswers>({});
const practiceResults = ref<Record<string, { correct: boolean }>>({});

function startPractice() {
  for (const key of Object.keys(practiceAnswers)) delete practiceAnswers[key];
  for (const b of wrongBlocks.value) {
    practiceAnswers[String(b.task.id)] = b.task.type === "order" ? { order: (b.task.items ?? []).map((i) => i.id) } : {};
  }
  practiceResults.value = {};
  mode.value = "practice";
  root.value?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function checkPractice() {
  busy.value = true;
  actionError.value = null;
  try {
    practiceResults.value = await practiceHomework(props.lessonId, practiceAnswers);
  } catch (e) {
    actionError.value = describeApiError(e, "Не удалось проверить.");
  } finally {
    busy.value = false;
  }
}

const allPracticeRight = computed(
  () => wrongBlocks.value.length > 0 && wrongBlocks.value.every((b) => practiceResults.value[String(b.task.id)]?.correct),
);
</script>

<template>
  <section v-if="loadError" class="card p-5 text-red-700 dark:text-red-400" role="alert">
    {{ loadError }} <button type="button" class="font-semibold underline" @click="load">Повторить</button>
  </section>

  <section v-else-if="s?.has_homework" ref="root" class="scroll-mt-24 space-y-4" aria-labelledby="hw-title">
    <!-- ── Running ── -->
    <template v-if="mode === 'running' && attempt">
      <div class="sticky top-[4.5rem] z-20 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-paper/95 px-4 py-3 shadow-sm backdrop-blur md:top-[7.5rem]">
        <h2 id="hw-title" class="font-bold text-ink">{{ title ?? "Домашнее задание" }}</h2>
        <div class="flex items-center gap-3">
          <span class="text-sm" :class="saveState === 'error' ? 'text-red-700 dark:text-red-400' : 'text-ink-3'" role="status">
            {{ saveState === "saving" ? "Сохраняется…" : saveState === "error" ? "Нет связи — ответы сохранятся позже" : saveState === "dirty" ? "Изменено" : "✓ Сохранено" }}
          </span>
          <span v-if="timeLeft != null && !showClock" class="text-sm text-ink-2">до срока {{ humanLeft(timeLeft) }}</span>
          <span
            v-if="showClock && timeLeft != null"
            class="rounded-xl px-3 py-1.5 font-mono text-lg font-bold tabular-nums"
            :class="timeLeft < 60_000 ? 'animate-pulse bg-red-100 dark:bg-red-500/15 text-red-700 dark:text-red-400' : timeLeft < 300_000 ? 'bg-amber-100 text-amber-900 dark:bg-amber-400/15 dark:text-amber-200' : 'bg-paper-2 text-ink'"
            :aria-label="`Осталось ${clockLeft(timeLeft)}`"
          >
            {{ clockLeft(timeLeft) }}
          </span>
        </div>
      </div>

      <HwAnswerTask
        v-for="(task, i) in attempt.tasks"
        :key="task.id"
        :task="task"
        :answer="answers[String(task.id)]"
        :number="i + 1"
        :uploading="uploading[task.id]"
        @upload="upload(task.id, $event)"
      />

      <div class="space-y-3 rounded-2xl border border-line bg-paper p-4">
        <p v-if="actionError" class="text-red-700 dark:text-red-400" role="alert">{{ actionError }}</p>
        <div v-if="confirmSubmit" class="space-y-3 rounded-xl bg-amber-50 p-3 text-amber-950 dark:bg-amber-400/10 dark:text-amber-100" role="alert">
          <p>Без ответа осталось заданий: <b>{{ unanswered }}</b>. Всё равно отправить?</p>
          <div class="flex flex-wrap gap-2">
            <button type="button" class="btn-primary min-h-12" :disabled="busy" @click="submit()">Да, отправить</button>
            <button type="button" class="btn-ghost min-h-12" @click="confirmSubmit = false">Вернуться к заданиям</button>
          </div>
        </div>
        <button v-else type="button" class="btn-primary min-h-14 w-full text-lg" :disabled="busy" @click="submit()">
          {{ busy ? "Отправляем…" : "Отправить ответы" }}
        </button>
        <p class="text-center text-sm text-ink-3">Ответы сохраняются сами — можно закрыть страницу и вернуться.</p>
      </div>
    </template>

    <!-- ── Practice ── -->
    <template v-else-if="mode === 'practice'">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h2 id="hw-title" class="text-xl font-bold text-ink">Работа над ошибками</h2>
        <button type="button" class="btn-ghost min-h-11" @click="mode = 'overview'">← К разбору</button>
      </div>
      <p class="rounded-xl bg-moss/10 px-4 py-3 text-moss">Только задания с ошибками. <b>На оценку не влияет</b> — это тренировка, можно решать сколько угодно раз.</p>
      <div v-for="(b, i) in wrongBlocks" :key="b.task.id" class="space-y-2">
        <HwAnswerTask :task="b.task" :answer="practiceAnswers[String(b.task.id)]" :number="i + 1" />
        <p v-if="practiceResults[String(b.task.id)]" class="px-1 font-semibold" :class="practiceResults[String(b.task.id)].correct ? 'text-moss' : 'text-red-700 dark:text-red-400'" role="status">
          {{ practiceResults[String(b.task.id)].correct ? "✓ Верно! Теперь вы это знаете." : "Пока неверно — загляните в разбор и попробуйте ещё." }}
        </p>
      </div>
      <p v-if="actionError" class="text-red-700 dark:text-red-400" role="alert">{{ actionError }}</p>
      <button type="button" class="btn-primary min-h-14 w-full text-lg" :disabled="busy" @click="checkPractice">
        {{ allPracticeRight ? "Все ошибки исправлены ✓" : "Проверить" }}
      </button>
    </template>

    <!-- ── Overview ── -->
    <template v-else>
      <div class="card space-y-4 p-5">
        <div class="flex flex-wrap items-start justify-between gap-2">
          <h2 id="hw-title" class="text-xl font-bold text-ink">{{ title ?? "Домашнее задание" }}</h2>
          <span v-if="s.phase === 'not_open'" class="badge bg-paper-2 text-ink-2">Ещё не открыто</span>
          <span v-else-if="s.phase === 'closed'" class="badge bg-paper-2 text-ink-2">Срок прошёл</span>
          <span v-else-if="s.open_attempt" class="badge bg-amber-100 text-amber-900 dark:bg-amber-400/15 dark:text-amber-200">Начато</span>
        </div>

        <p v-if="notice" class="rounded-xl bg-moss/10 px-4 py-3 font-medium text-moss" role="status">{{ notice }}</p>

        <ul class="flex flex-wrap gap-2 text-sm">
          <li v-if="s.phase === 'not_open' && s.opens_at" class="rounded-full bg-paper-2 px-3 py-1.5 font-medium">
            Откроется {{ formatKz(s.opens_at) }}<template v-if="opensLeft != null && opensLeft > 0"> · через {{ humanLeft(opensLeft) }}</template>
          </li>
          <li v-if="s.deadline" class="rounded-full px-3 py-1.5 font-medium" :class="deadlineLeft != null && deadlineLeft > 0 && deadlineLeft < 86_400_000 ? 'bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400' : 'bg-amber-100 text-amber-950 dark:bg-amber-400/15 dark:text-amber-100'">
            {{ s.phase === "closed" ? "Срок был" : "Сдать до" }} {{ formatKz(s.deadline) }}<template v-if="deadlineLeft != null && deadlineLeft > 0"> · осталось {{ humanLeft(deadlineLeft) }}</template>
          </li>
          <li v-else class="rounded-full bg-paper-2 px-3 py-1.5 font-medium">Без срока</li>
          <li class="rounded-full bg-paper-2 px-3 py-1.5 font-medium">{{ attemptsLine }}</li>
          <li v-if="s.time_limit_minutes" class="rounded-full bg-paper-2 px-3 py-1.5 font-medium">На попытку {{ s.time_limit_minutes }} мин</li>
          <li class="rounded-full bg-paper-2 px-3 py-1.5 font-medium">Заданий: {{ s.task_count }}</li>
        </ul>

        <!-- Result -->
        <div v-if="s.result" class="flex flex-wrap items-center gap-4 rounded-2xl bg-paper-2/60 p-4">
          <div class="text-center">
            <div class="text-4xl font-bold text-moss">{{ s.result.grade ?? "…" }}</div>
            <div class="text-xs text-ink-3">из 100</div>
          </div>
          <div class="min-w-0 flex-1 space-y-1">
            <p class="font-semibold text-ink">
              <template v-if="s.result.grade == null">Часть заданий ещё проверяет учитель</template>
              <template v-else-if="s.result.overridden">Оценка поставлена учителем</template>
              <template v-else>Ваша оценка</template>
            </p>
            <p v-if="(s.result.auto_max ?? 0) > 0" class="text-sm text-ink-2">
              Автопроверка (лучшая попытка): {{ formatPoints(s.result.auto_earned) }} из {{ formatPoints(s.result.auto_max) }}
            </p>
            <p v-if="s.result.manual_pending" class="text-sm text-amber-800 dark:text-amber-200">Развёрнутые ответы ожидают проверки учителем.</p>
            <p v-if="s.teacher_comment" class="text-sm text-ink-2">Комментарий учителя: {{ s.teacher_comment }}</p>
          </div>
        </div>
        <p v-if="s.decision === 'retake' && !s.result" class="rounded-xl bg-moss/10 px-4 py-3 text-moss">
          Учитель разрешил пересдать: у вас новый вариант.<template v-if="s.teacher_comment"> {{ s.teacher_comment }}</template>
        </p>

        <p v-if="revealLine" class="text-sm text-ink-2">{{ revealLine }}</p>
        <p v-if="s.reason && !s.can_start && s.phase !== 'not_open'" class="text-ink-2">{{ s.reason }}.</p>
        <p v-if="actionError" class="text-red-700 dark:text-red-400" role="alert">{{ actionError }}</p>

        <div v-if="s.can_start" class="space-y-2">
          <p v-if="s.time_limit_minutes && !s.open_attempt" class="text-sm text-ink-2">
            У вас будет {{ s.time_limit_minutes }} мин. Таймер начнётся сразу после нажатия «{{ startLabel }}».
          </p>
          <button type="button" class="btn-primary min-h-14 w-full text-lg sm:w-auto sm:px-10" :disabled="busy" @click="start">
            {{ busy ? "Открываем…" : startLabel }}
          </button>
        </div>
      </div>

      <!-- Review after the key opens -->
      <template v-if="s.reveal && s.review">
        <div class="flex flex-wrap items-center justify-between gap-2 pt-2">
          <h3 class="text-lg font-bold text-ink">Разбор вашей лучшей попытки</h3>
          <button v-if="wrongBlocks.length" type="button" class="btn-primary min-h-12" @click="startPractice">
            Работа над ошибками ({{ wrongBlocks.length }})
          </button>
        </div>
        <HwReviewTask v-for="(b, i) in s.review" :key="b.task.id" :block="b" :number="i + 1" />
      </template>
    </template>
  </section>
</template>
