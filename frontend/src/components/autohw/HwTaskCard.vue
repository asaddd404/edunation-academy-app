<script setup lang="ts">
import { isAxiosError } from "axios";
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";

import { createHomeworkTask, deleteHomeworkTask, updateHomeworkTask } from "@/api/autoHomework";
import HwTaskEditor from "@/components/autohw/HwTaskEditor.vue";
import type { HwTask, HwTaskData, HwTaskType } from "@/types/autoHomework";
import { describeApiError } from "@/utils/apiError";
import { HW_TYPES, blankTask, parseGapTemplate, pluralPoints, taskProblem } from "@/utils/hwTasks";

/**
 * One task in the homework constructor: a summary row, and when open, its
 * editor. Saves on its own a moment after the teacher stops typing --
 * there is no "Save" button to forget.
 *
 * Saving rules that keep it from losing or mangling work:
 *  - one request at a time; edits made while a save is in flight are sent
 *    right after it;
 *  - an incomplete task is not sent at all, the card says what's missing;
 *  - ids the server gives new options/pairs are copied into the draft, so
 *    the next save keeps them -- students' answers refer to those ids;
 *  - closing the card or leaving the page sends what's pending at once.
 */
const props = defineProps<{
  lessonId: number;
  task: HwTask | null;
  type: HwTaskType;
  number: number;
  isFirst: boolean;
  isLast: boolean;
  open: boolean;
}>();

const emit = defineEmits<{
  saved: [task: HwTask];
  toggle: [];
  remove: [];
  duplicate: [];
  move: [delta: -1 | 1];
}>();

function clone<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T;
}

const start = props.task ? { prompt: props.task.prompt, data: clone(props.task.data), points: props.task.points } : blankTask(props.type);
const draft = reactive<{ prompt: string; data: HwTaskData; points: number }>(start);

type SaveState = "saved" | "dirty" | "saving" | "incomplete" | "invalid" | "error";
const saveState = ref<SaveState>(props.task ? "saved" : "incomplete");
const message = ref<string | null>(props.task ? null : taskProblem(props.type, draft.prompt, draft.data));

let savedJson = props.task ? JSON.stringify(snapshot()) : "";
let timer: ReturnType<typeof setTimeout> | null = null;
let inFlight = false;
let again = false;
// A ref, not a plain variable: the buttons that need a saved task (copy,
// move) must notice the moment the first save lands.
const currentId = ref<number | null>(props.task?.id ?? null);
// Set once the teacher confirms deletion: nothing may be saved after that,
// or a pending draft would be created right after it was "deleted".
let removed = false;

function snapshot() {
  return { prompt: draft.prompt, data: clone(draft.data), points: draft.points };
}

watch(
  draft,
  () => {
    const problem = taskProblem(props.type, draft.prompt, draft.data);
    if (problem) {
      saveState.value = "incomplete";
      message.value = problem;
      if (timer) clearTimeout(timer);
      return;
    }
    if (JSON.stringify(snapshot()) === savedJson) {
      saveState.value = "saved";
      message.value = null;
      return;
    }
    saveState.value = "dirty";
    message.value = null;
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => void flush(), 800);
  },
  { deep: true },
);

async function flush() {
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  if (removed) return;
  if (inFlight) {
    again = true;
    return;
  }
  if (taskProblem(props.type, draft.prompt, draft.data)) return;
  const body = snapshot();
  const json = JSON.stringify(body);
  if (json === savedJson) return;
  inFlight = true;
  saveState.value = "saving";
  try {
    const saved = currentId.value
      ? await updateHomeworkTask(currentId.value, body)
      : await createHomeworkTask(props.lessonId, { type: props.type, ...body });
    if (removed) {
      // Deleted while this save was on its way: undo a fresh create, and
      // let the parent's delete handle an existing task.
      if (!currentId.value) void deleteHomeworkTask(saved.id).catch(() => undefined);
      return;
    }
    currentId.value = saved.id;
    adoptIds(draft.data, saved.data);
    if (props.type === "essay") draft.points = saved.points;
    // The baseline is what was SENT (plus the ids the server gave it), not
    // the draft now: edits made while the request was out must still differ
    // from it, so the follow-up save really sends them.
    adoptIds(body.data, saved.data);
    if (props.type === "essay") body.points = saved.points;
    savedJson = JSON.stringify(body);
    // Edited again while the request was out: the next save carries it.
    saveState.value = JSON.stringify(snapshot()) === savedJson ? "saved" : "dirty";
    message.value = null;
    emit("saved", saved);
  } catch (e) {
    const status = isAxiosError(e) ? e.response?.status : undefined;
    saveState.value = status === 422 ? "invalid" : "error";
    message.value = describeApiError(e, "Не удалось сохранить задание.");
  } finally {
    inFlight = false;
    if (again) {
      again = false;
      void flush();
    }
  }
}

/** Copy ids/rids the server minted for new rows into the draft, by position. */
function adoptIds(target: HwTaskData, server: HwTaskData) {
  for (const key of ["options", "pairs", "items", "criteria"] as const) {
    const mine = target[key] as { id?: string; rid?: string }[] | undefined;
    const theirs = server[key] as { id?: string; rid?: string }[] | undefined;
    if (!mine || !theirs) continue;
    mine.forEach((row, i) => {
      if (!row.id && theirs[i]?.id) row.id = theirs[i].id;
      if (key === "pairs" && !row.rid && theirs[i]?.rid) row.rid = theirs[i].rid;
    });
  }
}

watch(
  () => props.open,
  (open) => {
    if (!open) void flush();
  },
);

function onLeave() {
  if (timer) void flush();
}
window.addEventListener("pagehide", onLeave);
onBeforeUnmount(() => {
  window.removeEventListener("pagehide", onLeave);
  if (timer) void flush();
});

defineExpose({ flush, isSaved: () => saveState.value === "saved" });

const meta = computed(() => HW_TYPES[props.type]);

const summary = computed(() => {
  if (props.type === "gaps") {
    const text = parseGapTemplate(draft.data.text ?? "")
      .segments.map((s) => ("t" in s ? s.t : "___"))
      .join("");
    return text.trim() || "Текст ещё не вставлен";
  }
  return draft.prompt.trim() || "Вопрос ещё не написан";
});

const pointsShown = computed(() =>
  props.type === "essay" && (draft.data.criteria ?? []).length
    ? (draft.data.criteria ?? []).reduce((s, c) => s + (Number(c.points) || 0), 0)
    : draft.points,
);

const confirmingDelete = ref(false);

function confirmRemove() {
  removed = true;
  if (timer) clearTimeout(timer);
  timer = null;
  confirmingDelete.value = false;
  emit("remove");
}
const unsaved = computed(() => currentId.value === null);
</script>

<template>
  <article
    class="rounded-2xl bg-paper transition-shadow"
    :class="open ? 'border-2 border-moss shadow-md' : 'border border-line'"
    :aria-label="`Задание ${number}: ${meta.label}`"
  >
    <div class="flex flex-wrap items-center gap-3 p-4">
      <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-moss text-base font-bold text-moss-fg">{{ number }}</span>
      <div class="min-w-0 flex-1 basis-64">
        <div class="flex flex-wrap items-center gap-2">
          <b class="text-ink">{{ meta.label }}</b>
          <span
            class="rounded-full px-2.5 py-0.5 text-xs font-bold"
            :class="meta.auto ? 'bg-moss/15 text-moss' : 'bg-amber-100 text-amber-900 dark:bg-amber-400/15 dark:text-amber-200'"
          >
            {{ meta.auto ? "Авто" : "Проверяете вы" }}
          </span>
        </div>
        <p class="truncate text-sm text-ink-3">{{ summary }} · {{ pointsShown }} {{ pluralPoints(pointsShown) }}</p>
      </div>

      <span v-if="saveState === 'saving'" class="text-sm text-ink-3" role="status">Сохраняется…</span>
      <span v-else-if="saveState === 'saved'" class="text-sm text-moss" role="status">✓ Сохранено</span>
      <span v-else-if="saveState === 'incomplete' || saveState === 'invalid'" class="text-sm font-medium text-amber-700 dark:text-amber-300" role="status">
        {{ unsaved ? "Ещё не сохранено" : "Изменения не сохранены" }}
      </span>
      <span v-else-if="saveState === 'error'" class="text-sm font-medium text-red-700 dark:text-red-400" role="status">Ошибка сохранения</span>

      <div class="flex flex-wrap gap-1.5">
        <button type="button" class="min-h-10 rounded-lg border border-line px-2.5 text-sm font-medium hover:bg-paper-2 disabled:opacity-40" :disabled="isFirst || unsaved" @click="emit('move', -1)">↑ Выше</button>
        <button type="button" class="min-h-10 rounded-lg border border-line px-2.5 text-sm font-medium hover:bg-paper-2 disabled:opacity-40" :disabled="isLast || unsaved" @click="emit('move', 1)">↓ Ниже</button>
        <button type="button" class="min-h-10 rounded-lg border border-line px-2.5 text-sm font-medium hover:bg-paper-2 disabled:opacity-40" :disabled="unsaved" @click="emit('duplicate')">Копия</button>
        <button type="button" class="min-h-10 rounded-lg border border-red-200 dark:border-red-500/30 px-2.5 text-sm font-medium text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10" @click="confirmingDelete = true">Удалить</button>
        <button type="button" class="min-h-10 rounded-lg bg-moss/10 px-3.5 text-sm font-bold text-moss hover:bg-moss/15" :aria-expanded="open" @click="emit('toggle')">
          {{ open ? "Свернуть" : "Изменить" }}
        </button>
      </div>
    </div>

    <div v-if="confirmingDelete" class="mx-4 mb-4 flex flex-wrap items-center gap-3 rounded-xl bg-red-50 dark:bg-red-500/10 p-3" role="alert">
      <span class="flex-1 font-medium text-ink">Удалить задание {{ number }} «{{ meta.label }}»?</span>
      <button type="button" class="btn-danger min-h-11" @click="confirmRemove">Да, удалить</button>
      <button type="button" class="btn-ghost min-h-11" @click="confirmingDelete = false">Не удалять</button>
    </div>

    <div v-if="message && (open || saveState === 'error')" class="mx-4 mb-3 rounded-xl px-4 py-3" :class="saveState === 'error' ? 'bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400' : 'bg-amber-50 text-amber-900 dark:bg-amber-400/10 dark:text-amber-200'" role="status">
      {{ saveState === "error" ? message : `Чтобы сохранить: ${message}` }}
      <button v-if="saveState === 'error'" type="button" class="ml-2 font-semibold underline" @click="flush">Повторить</button>
    </div>

    <div v-if="open" class="border-t border-line p-4 sm:p-5">
      <HwTaskEditor :type="type" :draft="draft" />
    </div>
  </article>
</template>
