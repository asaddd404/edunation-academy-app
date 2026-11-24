<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { deleteHomeworkTask, duplicateHomeworkTask, getTeacherHomework, reorderHomeworkTasks } from "@/api/autoHomework";
import HwSettings from "@/components/autohw/HwSettings.vue";
import HwTaskCard from "@/components/autohw/HwTaskCard.vue";
import { useToastStore } from "@/stores/toast";
import type { HwSettings as HwSettingsT, HwTask, HwTaskType } from "@/types/autoHomework";
import { describeApiError } from "@/utils/apiError";
import { HW_TYPES, HW_TYPE_ORDER, pluralPoints } from "@/utils/hwTasks";

/**
 * The homework constructor for one lesson: the tasks (any of nine types,
 * in any order), the "add a task" picker, and the timing settings.
 */
const props = defineProps<{ lessonId: number }>();
const toast = useToastStore();

interface Row {
  key: string; // stable across the create: a draft keeps its key once saved
  type: HwTaskType;
  task: HwTask | null;
}

const rows = ref<Row[]>([]);
const settings = ref<HwSettingsT | null>(null);
const openKey = ref<string | null>(null);
const loading = ref(true);
const loadError = ref<string | null>(null);
let seq = 0;

async function load() {
  loading.value = true;
  loadError.value = null;
  try {
    const hw = await getTeacherHomework(props.lessonId);
    settings.value = hw.settings;
    rows.value = hw.tasks.map((t) => ({ key: `t${t.id}`, type: t.type, task: t }));
  } catch (e) {
    loadError.value = describeApiError(e, "Не удалось загрузить домашку.");
  } finally {
    loading.value = false;
  }
}
onMounted(load);

const savedRows = computed(() => rows.value.filter((r) => r.task));
const totalPoints = computed(() => savedRows.value.reduce((s, r) => s + (r.task?.points ?? 0), 0));
const autoCount = computed(() => savedRows.value.filter((r) => r.task?.auto).length);
const manualCount = computed(() => savedRows.value.length - autoCount.value);

function add(type: HwTaskType) {
  const key = `d${++seq}`;
  rows.value.push({ key, type, task: null });
  openKey.value = key;
  // Bring the new card into view: on a long list it opens off screen.
  requestAnimationFrame(() => document.getElementById(`hw-${key}`)?.scrollIntoView({ behavior: "smooth", block: "center" }));
}

function onSaved(row: Row, task: HwTask) {
  row.task = task;
}

function toggle(row: Row) {
  openKey.value = openKey.value === row.key ? null : row.key;
}

async function remove(row: Row) {
  const index = rows.value.indexOf(row);
  if (index < 0) return;
  rows.value.splice(index, 1);
  if (!row.task) return;
  try {
    await deleteHomeworkTask(row.task.id);
  } catch (e) {
    rows.value.splice(index, 0, row); // put it back: it still exists
    toast.push(describeApiError(e, "Не удалось удалить задание."));
  }
}

async function duplicate(row: Row) {
  if (!row.task) return;
  try {
    const copy = await duplicateHomeworkTask(row.task.id);
    const index = rows.value.indexOf(row);
    const key = `t${copy.id}`;
    rows.value.splice(index + 1, 0, { key, type: copy.type, task: copy });
    openKey.value = key;
  } catch (e) {
    toast.push(describeApiError(e, "Не удалось скопировать задание."));
  }
}

async function move(row: Row, delta: -1 | 1) {
  const index = rows.value.indexOf(row);
  const target = index + delta;
  if (target < 0 || target >= rows.value.length) return;
  const before = rows.value.slice();
  const next = rows.value.slice();
  [next[index], next[target]] = [next[target], next[index]];
  rows.value = next;
  const ids = next.filter((r) => r.task).map((r) => r.task!.id);
  try {
    await reorderHomeworkTasks(props.lessonId, ids);
  } catch (e) {
    rows.value = before;
    toast.push(describeApiError(e, "Не удалось поменять порядок."));
    if (String(describeApiError(e)).includes("обновите")) void load();
  }
}
</script>

<template>
  <div class="space-y-6">
    <div v-if="loading" class="space-y-3" aria-busy="true">
      <div class="h-20 animate-pulse rounded-2xl bg-paper-2" />
      <div class="h-20 animate-pulse rounded-2xl bg-paper-2" />
    </div>

    <div v-else-if="loadError" class="rounded-2xl bg-red-50 dark:bg-red-500/10 p-4 text-red-700 dark:text-red-400" role="alert">
      {{ loadError }} <button type="button" class="font-semibold underline" @click="load">Повторить</button>
    </div>

    <template v-else>
      <section class="space-y-3" aria-labelledby="hw-tasks-title">
        <div class="flex flex-wrap items-baseline justify-between gap-2">
          <h3 id="hw-tasks-title" class="text-xl font-bold text-ink">Задания домашки ({{ rows.length }})</h3>
          <p v-if="savedRows.length" class="text-ink-2">
            Всего {{ totalPoints }} {{ pluralPoints(totalPoints) }} ·
            {{ manualCount ? `${autoCount} проверятся сами, ${manualCount} проверяете вы` : "всё проверится само" }}
          </p>
        </div>
        <p v-if="!rows.length" class="rounded-2xl border-2 border-dashed border-line-strong p-6 text-center text-ink-2">
          Заданий пока нет. Выберите тип ниже — например, «Заполните пропуски».
        </p>
        <div v-for="(row, i) in rows" :id="`hw-${row.key}`" :key="row.key">
          <HwTaskCard
            :lesson-id="lessonId"
            :task="row.task"
            :type="row.type"
            :number="i + 1"
            :is-first="i === 0"
            :is-last="i === rows.length - 1"
            :open="openKey === row.key"
            @saved="onSaved(row, $event)"
            @toggle="toggle(row)"
            @remove="remove(row)"
            @duplicate="duplicate(row)"
            @move="move(row, $event)"
          />
        </div>
      </section>

      <section class="space-y-3 rounded-2xl border-2 border-dashed border-moss/40 bg-paper-2/40 p-4 sm:p-5" aria-labelledby="hw-add-title">
        <h3 id="hw-add-title" class="text-lg font-bold text-ink">+ Добавить задание — выберите тип</h3>
        <div class="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
          <button
            v-for="type in HW_TYPE_ORDER"
            :key="type"
            type="button"
            class="flex min-h-[4.5rem] flex-col items-start gap-1 rounded-2xl border-2 border-line bg-paper p-3.5 text-left transition-colors hover:border-moss/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-moss"
            :disabled="rows.length >= 60"
            @click="add(type)"
          >
            <span class="flex flex-wrap items-center gap-2">
              <b class="text-ink">{{ HW_TYPES[type].label }}</b>
              <span
                class="rounded-full px-2 py-0.5 text-xs font-bold"
                :class="HW_TYPES[type].auto ? 'bg-moss/15 text-moss' : 'bg-amber-100 text-amber-900 dark:bg-amber-400/15 dark:text-amber-200'"
              >
                {{ HW_TYPES[type].auto ? "Авто" : "Проверяете вы" }}
              </span>
            </span>
            <span class="text-sm text-ink-2">{{ HW_TYPES[type].desc }}</span>
          </button>
        </div>
        <p class="text-sm text-ink-2">
          «Авто» — проверяется сразу после отправки. «Проверяете вы» — ученик увидит «Ожидает проверки», а итоговая оценка сложится из обеих частей.
        </p>
      </section>

      <HwSettings v-if="settings" :lesson-id="lessonId" :settings="settings" :task-count="savedRows.length" @saved="settings = $event" />

      <router-link
        v-if="savedRows.length"
        :to="`/teacher/lessons/${lessonId}/homework`"
        class="flex min-h-12 items-center justify-center rounded-xl border-2 border-moss px-5 font-bold text-moss hover:bg-moss/5"
      >
        Результаты учеников →
      </router-link>
    </template>
  </div>
</template>
