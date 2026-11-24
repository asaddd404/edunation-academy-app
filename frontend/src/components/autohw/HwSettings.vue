<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, useId, watch } from "vue";

import { saveHomeworkSettings } from "@/api/autoHomework";
import HwToggle from "@/components/autohw/HwToggle.vue";
import type { HwSettings } from "@/types/autoHomework";
import { describeApiError } from "@/utils/apiError";
import { fromKzParts, toKzParts } from "@/utils/hwTasks";

/**
 * When the homework opens and closes, how long an attempt lasts, how many
 * attempts, and whether each student gets their own variant. Every rule can
 * be switched off; all of it can change while students are working, and
 * open attempts follow straight away (the server moves their end time).
 */
const props = defineProps<{ lessonId: number; settings: HwSettings; taskCount: number }>();
const emit = defineEmits<{ saved: [settings: HwSettings] }>();
const uid = useId();

const opens = toKzParts(props.settings.opens_at);
const due = toKzParts(props.settings.deadline);

const form = reactive({
  opensOn: !!props.settings.opens_at,
  opensDate: opens.date,
  opensTime: opens.time || "08:00",
  deadlineOn: !!props.settings.deadline,
  deadlineDate: due.date,
  deadlineTime: due.time || "23:59",
  timerOn: !!props.settings.time_limit_minutes,
  minutes: props.settings.time_limit_minutes ?? 20,
  unlimited: props.settings.max_attempts === null,
  attempts: props.settings.max_attempts ?? 3,
  variantOn: !!props.settings.tasks_per_student,
  perStudent: props.settings.tasks_per_student ?? Math.max(1, Math.min(props.taskCount, 5)),
});

function payload(): HwSettings {
  return {
    opens_at: form.opensOn ? fromKzParts(form.opensDate, form.opensTime) : null,
    deadline: form.deadlineOn ? fromKzParts(form.deadlineDate, form.deadlineTime) : null,
    time_limit_minutes: form.timerOn ? Math.round(form.minutes) : null,
    max_attempts: form.unlimited ? null : Math.round(form.attempts),
    tasks_per_student: form.variantOn ? Math.round(form.perStudent) : null,
  };
}

const problem = computed<string | null>(() => {
  if (form.opensOn && !form.opensDate) return "Выберите дату открытия.";
  if (form.deadlineOn && !form.deadlineDate) return "Выберите дату срока сдачи.";
  if (form.timerOn && !(form.minutes >= 1 && form.minutes <= 600)) return "Время на попытку — от 1 до 600 минут.";
  if (!form.unlimited && !(form.attempts >= 1 && form.attempts <= 20)) return "Попыток — от 1 до 20.";
  if (form.variantOn && !(form.perStudent >= 1)) return "Сколько заданий давать каждому — хотя бы 1.";
  const p = payload();
  if (p.opens_at && p.deadline && new Date(p.deadline) <= new Date(p.opens_at)) return "Срок сдачи должен быть позже даты открытия.";
  return null;
});

const state = ref<"saved" | "dirty" | "saving" | "error">("saved");
const error = ref<string | null>(null);
let savedJson = JSON.stringify(payload());
let timer: ReturnType<typeof setTimeout> | null = null;
let inFlight = false;
let again = false;

watch(
  form,
  () => {
    if (problem.value) return;
    if (JSON.stringify(payload()) === savedJson) {
      state.value = "saved";
      return;
    }
    state.value = "dirty";
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => void save(), 700);
  },
  { deep: true },
);

async function save() {
  if (timer) clearTimeout(timer);
  timer = null;
  if (problem.value) return;
  if (inFlight) {
    again = true;
    return;
  }
  const body = payload();
  const json = JSON.stringify(body);
  if (json === savedJson) return;
  inFlight = true;
  state.value = "saving";
  try {
    const saved = await saveHomeworkSettings(props.lessonId, body);
    savedJson = json;
    state.value = JSON.stringify(payload()) === savedJson ? "saved" : "dirty";
    error.value = null;
    emit("saved", saved);
  } catch (e) {
    state.value = "error";
    error.value = describeApiError(e, "Не удалось сохранить настройки.");
  } finally {
    inFlight = false;
    if (again) {
      again = false;
      void save();
    }
  }
}

onBeforeUnmount(() => {
  if (timer) void save();
});

function step(field: "attempts" | "minutes" | "perStudent", delta: number, lo: number, hi: number) {
  form[field] = Math.min(hi, Math.max(lo, Math.round(Number(form[field]) || lo) + delta));
}

const revealHint = computed(() => {
  if (form.deadlineOn) return "Правильные ответы ученики увидят только после срока сдачи (и после всех личных продлений) — до этого им нечего пересылать друг другу.";
  if (form.unlimited) return "Без срока и без лимита попыток правильные ответы открываются только тем, кто решил всё верно — иначе их можно было бы передать.";
  return "Без срока ученик увидит правильные ответы, когда использует все попытки. Свой вариант у каждого защитит от пересылки.";
});
</script>

<template>
  <section class="space-y-5 rounded-2xl border border-line bg-paper p-5" aria-labelledby="hw-settings-title">
    <div class="flex flex-wrap items-start justify-between gap-2">
      <div>
        <h3 id="hw-settings-title" class="text-lg font-bold text-ink">Когда сдавать и сколько попыток</h3>
        <p class="text-sm text-ink-3">Всё можно менять в любой момент — даже когда ученики уже решают. Изменения применятся сразу.</p>
      </div>
      <span v-if="state === 'saving'" class="text-sm text-ink-3" role="status">Сохраняется…</span>
      <span v-else-if="state === 'saved'" class="text-sm text-moss" role="status">✓ Сохранено</span>
    </div>

    <p v-if="problem" class="rounded-xl bg-amber-50 px-4 py-3 text-amber-900 dark:bg-amber-400/10 dark:text-amber-200" role="status">{{ problem }}</p>
    <p v-if="error" class="rounded-xl bg-red-50 dark:bg-red-500/10 px-4 py-3 text-red-700 dark:text-red-400" role="alert">
      {{ error }} <button type="button" class="font-semibold underline" @click="save">Повторить</button>
    </p>

    <!-- Opening date -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="min-w-0 flex-1 basis-72">
        <p class="font-semibold text-ink">Открыть не сразу, а с определённого дня</p>
        <p class="text-sm text-ink-3">До этого ученики увидят, когда задание откроется</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <template v-if="form.opensOn">
          <input v-model="form.opensDate" type="date" class="input min-h-11 w-auto text-base" aria-label="Дата открытия" />
          <input v-model="form.opensTime" type="time" class="input min-h-11 w-auto text-base" aria-label="Время открытия" />
        </template>
        <HwToggle v-model="form.opensOn" label="Открыть с определённого дня" />
      </div>
    </div>

    <!-- Deadline -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="min-w-0 flex-1 basis-72">
        <p class="font-semibold text-ink">Срок сдачи (дедлайн)</p>
        <p class="text-sm text-ink-3">
          {{ form.deadlineOn ? "После срока сдать нельзя. Заболевшему ученику срок можно продлить отдельно в «Результатах»." : "Без срока: ученик сдаёт, когда удобно." }}
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <template v-if="form.deadlineOn">
          <input v-model="form.deadlineDate" type="date" class="input min-h-11 w-auto text-base" aria-label="Дата срока сдачи" />
          <input v-model="form.deadlineTime" type="time" class="input min-h-11 w-auto text-base" aria-label="Время срока сдачи" />
        </template>
        <HwToggle v-model="form.deadlineOn" label="Срок сдачи" />
      </div>
    </div>
    <p class="-mt-2 text-sm text-ink-3">Время — по Казахстану (UTC+5).</p>

    <!-- Time limit -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="min-w-0 flex-1 basis-72">
        <p class="font-semibold text-ink">Ограничить время на попытку</p>
        <p class="text-sm text-ink-3">
          {{ form.timerOn ? "Таймер идёт с момента открытия задания. Когда время выйдет, сохранённые ответы отправятся сами." : "Без ограничения — решает сколько нужно." }}
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <template v-if="form.timerOn">
          <button type="button" class="flex h-11 w-11 items-center justify-center rounded-lg border-2 border-line-strong text-xl" aria-label="Меньше минут" @click="step('minutes', -5, 1, 600)">−</button>
          <input :id="`${uid}-min`" v-model.number="form.minutes" type="number" min="1" max="600" inputmode="numeric" class="input min-h-11 w-20 text-center text-base" aria-label="Минут на попытку" />
          <button type="button" class="flex h-11 w-11 items-center justify-center rounded-lg border-2 border-line-strong text-xl" aria-label="Больше минут" @click="step('minutes', 5, 1, 600)">+</button>
          <span>мин</span>
        </template>
        <HwToggle v-model="form.timerOn" label="Ограничить время на попытку" />
      </div>
    </div>

    <!-- Attempts -->
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="min-w-0 flex-1 basis-72">
        <p class="font-semibold text-ink">Сколько раз можно отправить ответ</p>
        <p class="text-sm text-ink-3">В зачёт идёт лучшая попытка</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button
          type="button"
          class="min-h-11 rounded-xl border-2 px-4 font-semibold"
          :class="form.unlimited ? 'border-moss bg-moss/10 text-moss' : 'border-line-strong'"
          :aria-pressed="form.unlimited"
          @click="form.unlimited = !form.unlimited"
        >
          Без ограничений
        </button>
        <template v-if="!form.unlimited">
          <button type="button" class="flex h-11 w-11 items-center justify-center rounded-lg border-2 border-line-strong text-xl" aria-label="Меньше попыток" @click="step('attempts', -1, 1, 20)">−</button>
          <span class="min-w-8 text-center text-xl font-bold" aria-live="polite">{{ form.attempts }}</span>
          <button type="button" class="flex h-11 w-11 items-center justify-center rounded-lg border-2 border-line-strong text-xl" aria-label="Больше попыток" @click="step('attempts', 1, 1, 20)">+</button>
        </template>
      </div>
    </div>

    <!-- Own variant -->
    <div class="space-y-2">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="min-w-0 flex-1 basis-72">
          <p class="font-semibold text-ink">Каждому ученику — свой вариант</p>
          <p class="text-sm text-ink-3">Задания выбираются случайно из всех, что вы добавили. Вариант не меняется между попытками.</p>
        </div>
        <HwToggle v-model="form.variantOn" label="Каждому ученику свой вариант" :disabled="taskCount < 2" />
      </div>
      <div v-if="form.variantOn" class="flex flex-wrap items-center gap-2">
        <span>Давать</span>
        <button type="button" class="flex h-11 w-11 items-center justify-center rounded-lg border-2 border-line-strong text-xl" aria-label="Меньше заданий" @click="step('perStudent', -1, 1, Math.max(1, taskCount))">−</button>
        <span class="min-w-8 text-center text-xl font-bold">{{ form.perStudent }}</span>
        <button type="button" class="flex h-11 w-11 items-center justify-center rounded-lg border-2 border-line-strong text-xl" aria-label="Больше заданий" @click="step('perStudent', 1, 1, Math.max(1, taskCount))">+</button>
        <span>заданий из {{ taskCount }}</span>
        <span v-if="form.perStudent >= taskCount" class="text-sm text-amber-700 dark:text-amber-300">— сейчас все получат одинаковые задания, добавьте ещё</span>
      </div>
      <p v-else-if="taskCount < 2" class="text-sm text-ink-3">Станет доступно, когда заданий будет хотя бы два.</p>
    </div>

    <p class="rounded-xl bg-paper-2 px-4 py-3 text-sm text-ink-2">{{ revealHint }}</p>
  </section>
</template>
