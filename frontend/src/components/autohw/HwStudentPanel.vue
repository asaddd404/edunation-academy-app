<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";

import {
  type HwDecisionAction,
  decideHomework,
  extendHomework,
  fetchHomeworkTaskFile,
  getHomeworkStudent,
  gradeManualTask,
} from "@/api/autoHomework";
import HwReviewTask from "@/components/autohw/HwReviewTask.vue";
import FilePreviewModal from "@/components/homework/FilePreviewModal.vue";
import type { HwResultRow, HwStudentDetail, HwStudentDetailBlock } from "@/types/autoHomework";
import { describeApiError } from "@/utils/apiError";
import { formatKz, formatPoints, fromKzParts, pluralPoints, toKzParts } from "@/utils/hwTasks";

/**
 * One student's work, opened from the results list: their answers with the
 * key, marks for essay/file tasks, the teacher's decision, a personal
 * deadline extension. Emits `changed` so the list refreshes its row.
 */
const props = defineProps<{ lessonId: number; row: HwResultRow }>();
const emit = defineEmits<{ changed: [] }>();

const detail = ref<HwStudentDetail | null>(null);
const error = ref<string | null>(null);
const busy = ref(false);
const message = ref<string | null>(null);

async function load() {
  error.value = null;
  try {
    detail.value = await getHomeworkStudent(props.lessonId, props.row.student.id);
    resetManual();
  } catch (e) {
    error.value = describeApiError(e, "Не удалось загрузить работу ученика.");
  }
}
onMounted(load);

async function run(action: () => Promise<unknown>, done: string) {
  busy.value = true;
  error.value = null;
  message.value = null;
  try {
    await action();
    message.value = done;
    await load();
    emit("changed");
  } catch (e) {
    error.value = describeApiError(e);
  } finally {
    busy.value = false;
  }
}

// ── decisions ──
const editing = ref(false);
const newGrade = ref<number | null>(null);
const comment = ref("");

function decide(action: HwDecisionAction) {
  const body: { action: HwDecisionAction; grade?: number; comment?: string } = { action };
  if (action === "edit") body.grade = Number(newGrade.value);
  if (comment.value.trim()) body.comment = comment.value.trim();
  const done: Record<HwDecisionAction, string> = {
    keep: "Отметка снята, оценка оставлена.",
    zero: "Оценка обнулена — ученик получил уведомление.",
    edit: "Оценка изменена — ученик получил уведомление.",
    retake: "Ученик пересдаёт новый вариант — он получил уведомление.",
    undo: "Решение отменено.",
  };
  void run(() => decideHomework(props.lessonId, props.row.student.id, body), done[action]).then(() => {
    editing.value = false;
    comment.value = "";
  });
}

const decisionText = computed(() => {
  const r = detail.value?.record;
  if (!r?.decision) return null;
  return {
    keep: "Вы оставили оценку и сняли отметку о списывании.",
    zero: "Оценка обнулена.",
    edit: `Оценка изменена на ${r.override_grade}/100.`,
    retake: "Ученик пересдаёт новый вариант, прежние попытки не считаются.",
  }[r.decision as "keep" | "zero" | "edit" | "retake"];
});
const canUndo = computed(() => {
  const r = detail.value?.record;
  if (!r?.decision) return false;
  return r.decision !== "retake" || r.can_undo_retake;
});

// ── extension ──
const ext = reactive({ date: "", time: "23:59" });
const extParts = toKzParts(props.row.extended_until);
ext.date = extParts.date;
ext.time = extParts.time || "23:59";

function extend(clear = false) {
  const until = clear ? null : fromKzParts(ext.date, ext.time);
  if (!clear && !until) {
    error.value = "Выберите новую дату.";
    return;
  }
  void run(() => extendHomework(props.lessonId, props.row.student.id, until), clear ? "Личный срок убран." : "Срок продлён — ученик получил уведомление.");
}

// ── manual marks (essay/file of the latest attempt) ──
const manualDraft = reactive<Record<number, { earned: number | null; criteria: string[] }>>({});

function resetManual() {
  for (const b of detail.value?.latest ?? []) {
    if (b.task_full.type !== "essay" && b.task_full.type !== "file") continue;
    manualDraft[b.task_full.id] = { earned: b.manual?.earned ?? null, criteria: [...(b.manual?.criteria ?? [])] };
  }
}

function criteriaSum(b: HwStudentDetailBlock): number {
  const chosen = new Set(manualDraft[b.task_full.id]?.criteria ?? []);
  return (b.task_full.data.criteria ?? []).filter((c) => c.id && chosen.has(c.id)).reduce((s, c) => s + c.points, 0);
}

function toggleCriterion(b: HwStudentDetailBlock, id: string) {
  const d = manualDraft[b.task_full.id];
  d.criteria = d.criteria.includes(id) ? d.criteria.filter((x) => x !== id) : [...d.criteria, id];
}

function saveManual(b: HwStudentDetailBlock) {
  const d = manualDraft[b.task_full.id];
  const hasCriteria = (b.task_full.data.criteria ?? []).length > 0;
  if (!hasCriteria && (d.earned == null || Number.isNaN(Number(d.earned)))) {
    error.value = `Поставьте баллы от 0 до ${b.task_full.points}.`;
    return;
  }
  const body = hasCriteria ? { task_id: b.task_full.id, criteria: d.criteria } : { task_id: b.task_full.id, earned: Number(d.earned) };
  void run(() => gradeManualTask(props.lessonId, props.row.student.id, body), "Баллы сохранены.");
}

// ── files ──
const preview = ref<{ url: string; kind: "image" | "pdf"; name: string } | null>(null);
const objectUrls: string[] = [];

function kindOf(name: string | undefined): "image" | "pdf" | "document" {
  const ext = (name ?? "").split(".").pop()?.toLowerCase() ?? "";
  if (["jpg", "jpeg", "png"].includes(ext)) return "image";
  return ext === "pdf" ? "pdf" : "document";
}

async function openFile(b: HwStudentDetailBlock) {
  if (!detail.value?.latest_attempt_id) return;
  try {
    const url = await fetchHomeworkTaskFile(detail.value.latest_attempt_id, b.task_full.id, true);
    objectUrls.push(url);
    const name = b.answer.file_name ?? "файл";
    const kind = kindOf(name);
    if (kind === "document") {
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
    } else preview.value = { url, kind, name };
  } catch (e) {
    error.value = describeApiError(e, "Не удалось открыть файл.");
  }
}
onBeforeUnmount(() => objectUrls.forEach((u) => URL.revokeObjectURL(u)));

function duration(sec: number | null): string {
  if (sec == null) return "—";
  return sec < 60 ? `${sec} с` : `${Math.floor(sec / 60)} мин ${sec % 60 ? `${sec % 60} с` : ""}`.trim();
}
</script>

<template>
  <div class="space-y-4 rounded-2xl bg-paper-2/60 p-4">
    <p v-if="error" class="rounded-xl bg-red-50 dark:bg-red-500/10 px-4 py-3 text-red-700 dark:text-red-400" role="alert">{{ error }}</p>
    <p v-if="message" class="rounded-xl bg-moss/10 px-4 py-3 font-medium text-moss" role="status">{{ message }}</p>

    <template v-if="row.flags.length">
      <div class="space-y-1 rounded-xl bg-amber-50 px-4 py-3 text-amber-950 dark:bg-amber-400/10 dark:text-amber-100">
        <p v-for="(f, i) in row.flags" :key="i">⚑ {{ f }}</p>
        <p class="text-sm">Это только подсказка — оценка уже поставлена автоматически, делать ничего не обязательно.</p>
      </div>
    </template>

    <!-- Decision -->
    <div v-if="row.result || detail?.record.decision" class="space-y-3 rounded-xl bg-paper p-4">
      <p class="font-semibold text-ink">Решение по работе</p>
      <div v-if="decisionText" class="flex flex-wrap items-center gap-3">
        <span>✓ {{ decisionText }}</span>
        <button v-if="canUndo" type="button" class="btn-ghost min-h-11" :disabled="busy" @click="decide('undo')">Отменить решение</button>
        <span v-else class="text-sm text-ink-3">Ученик уже начал пересдачу — отменить нельзя.</span>
      </div>
      <template v-if="!detail?.record.decision || detail.record.decision === 'keep'">
        <div v-if="!editing" class="flex flex-wrap gap-2">
          <button v-if="row.flags.length" type="button" class="btn-ghost min-h-11" :disabled="busy" @click="decide('keep')">✓ Всё в порядке, оставить</button>
          <button type="button" class="btn-ghost min-h-11" :disabled="busy" @click="(editing = true), (newGrade = row.result?.grade ?? null)">Изменить оценку</button>
          <button type="button" class="btn-ghost min-h-11" :disabled="busy" @click="decide('retake')">Дать пересдать (новый вариант)</button>
          <button type="button" class="btn-danger min-h-11" :disabled="busy" @click="decide('zero')">Обнулить</button>
        </div>
        <div v-else class="space-y-3">
          <div class="flex flex-wrap items-center gap-2">
            <label :for="`grade-${row.student.id}`" class="font-medium">Новая оценка</label>
            <input :id="`grade-${row.student.id}`" v-model.number="newGrade" type="number" min="0" max="100" inputmode="numeric" class="input min-h-11 w-24 text-center text-base" />
            <span>/ 100</span>
          </div>
          <div class="space-y-1">
            <label :for="`comment-${row.student.id}`" class="font-medium">Комментарий для ученика <span class="font-normal text-ink-3">(необязательно)</span></label>
            <textarea :id="`comment-${row.student.id}`" v-model="comment" rows="2" maxlength="2000" class="input text-base" />
          </div>
          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              class="btn-primary min-h-11"
              :disabled="busy || newGrade == null || newGrade < 0 || newGrade > 100"
              @click="decide('edit')"
            >
              Сохранить оценку
            </button>
            <button type="button" class="btn-ghost min-h-11" @click="editing = false">Отмена</button>
          </div>
        </div>
      </template>
    </div>

    <!-- Extension -->
    <div class="flex flex-wrap items-center gap-2 rounded-xl bg-paper p-4">
      <span class="font-semibold">Личный срок сдачи:</span>
      <input v-model="ext.date" type="date" class="input min-h-11 w-auto text-base" :aria-label="`Новый срок для ${row.student.name}`" />
      <input v-model="ext.time" type="time" class="input min-h-11 w-auto text-base" aria-label="Время" />
      <button type="button" class="btn-primary min-h-11" :disabled="busy" @click="extend()">Продлить</button>
      <button v-if="row.extended_until" type="button" class="btn-ghost min-h-11" :disabled="busy" @click="extend(true)">Убрать</button>
      <span class="w-full text-sm text-ink-3">
        {{ row.extended_until ? `Сейчас: до ${formatKz(row.extended_until)}. ` : "" }}Правильные ответы остальным откроются после всех продлений.
      </span>
    </div>

    <p v-if="!detail && !error" class="text-ink-3" aria-busy="true">Загружаем работу…</p>

    <template v-if="detail">
      <div v-if="detail.attempts.length" class="rounded-xl bg-paper p-4 text-sm">
        <p class="mb-2 font-semibold text-ink">Попытки</p>
        <ul class="space-y-1">
          <li v-for="(a, i) in detail.attempts" :key="a.id" :class="a.counted ? 'text-ink' : 'text-ink-3 line-through'">
            {{ i + 1 }}. {{ formatKz(a.started_at) }} ·
            {{ a.status === "submitted" ? `${formatPoints(a.auto_earned)} из ${formatPoints(a.auto_max)} авто` : "в процессе" }}
            · {{ duration(a.duration_seconds) }}
            <template v-if="a.away_count"> · уходил(а) со страницы {{ a.away_count }} раз</template>
            <template v-if="!a.counted && a.status === 'submitted'"> (не считается — пересдача)</template>
          </li>
        </ul>
      </div>

      <template v-if="detail.latest">
        <p class="font-semibold text-ink">Ответы последней попытки</p>
        <HwReviewTask v-for="(b, i) in detail.latest" :key="b.task.id" :block="b" :number="i + 1">
          <!-- Marks for the teacher's part -->
          <div v-if="b.task_full.type === 'essay' || b.task_full.type === 'file'" class="space-y-3 rounded-xl border-2 border-amber-300 bg-amber-50/60 p-3 dark:border-amber-400/30 dark:bg-amber-400/5">
            <button v-if="b.task_full.type === 'file' && b.has_file" type="button" class="btn-ghost min-h-11" @click="openFile(b)">Открыть файл</button>
            <p v-if="b.items[0]?.words != null" class="text-sm text-ink-2">
              Слов: {{ b.items[0].words }}<template v-if="b.task_full.data.min_words"> (минимум {{ b.task_full.data.min_words }})</template>
            </p>
            <template v-if="(b.task_full.data.criteria ?? []).length">
              <p class="font-medium">Отметьте выполненные критерии:</p>
              <label v-for="c in b.task_full.data.criteria" :key="c.id" class="flex min-h-11 cursor-pointer items-center gap-3">
                <input type="checkbox" class="h-6 w-6 accent-moss" :checked="manualDraft[b.task_full.id]?.criteria.includes(c.id!)" @change="toggleCriterion(b, c.id!)" />
                <span>{{ c.text }} — {{ c.points }} {{ pluralPoints(c.points) }}</span>
              </label>
              <p class="font-semibold">Итого: {{ criteriaSum(b) }} из {{ b.task_full.points }}</p>
            </template>
            <div v-else class="flex flex-wrap items-center gap-2">
              <label :for="`m-${b.task_full.id}`" class="font-medium">Баллы:</label>
              <input
                :id="`m-${b.task_full.id}`"
                v-model.number="manualDraft[b.task_full.id].earned"
                type="number"
                min="0"
                :max="b.task_full.points"
                step="0.5"
                inputmode="decimal"
                class="input min-h-11 w-24 text-center text-base"
              />
              <span>из {{ b.task_full.points }}</span>
            </div>
            <button type="button" class="btn-primary min-h-11" :disabled="busy" @click="saveManual(b)">
              {{ b.manual ? "Изменить баллы" : "Сохранить баллы" }}
            </button>
          </div>
        </HwReviewTask>
      </template>
      <p v-else class="text-ink-2">Ученик ещё не отправлял ответы.</p>
    </template>

    <FilePreviewModal v-if="preview" :url="preview.url" :kind="preview.kind" :name="preview.name" @close="preview = null" @download="() => undefined" />
  </div>
</template>
