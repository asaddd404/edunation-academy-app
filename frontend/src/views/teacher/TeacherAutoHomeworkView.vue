<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import { addTimeToOpenAttempts, getHomeworkProblems, getHomeworkResults, getTeacherHomework } from "@/api/autoHomework";
import HwSettings from "@/components/autohw/HwSettings.vue";
import HwStudentPanel from "@/components/autohw/HwStudentPanel.vue";
import PageContainer from "@/components/layout/PageContainer.vue";
import BackLink from "@/components/ui/BackLink.vue";
import type { HwProblem, HwResultRow, HwResults, HwSettings as HwSettingsT } from "@/types/autoHomework";
import { describeApiError } from "@/utils/apiError";
import { formatKz } from "@/utils/hwTasks";

/**
 * Results of one lesson's auto-checked homework: who handed in what, the
 * copy hints, the teacher's decisions, and where the class went wrong.
 */
const route = useRoute();
const lessonId = Number(route.params.id);

const results = ref<HwResults | null>(null);
const problems = ref<HwProblem[] | null>(null);
const error = ref<string | null>(null);
const view = ref<"students" | "problems">(route.query.tab === "problems" ? "problems" : "students");
const filter = ref<"all" | "done" | "not" | "manual" | "flag">("all");
const openId = ref<number | null>(null);
const settingsOpen = ref(false);
const settings = ref<HwSettingsT | null>(null);
const taskCount = ref(0);
const notice = ref<string | null>(null);

async function load() {
  error.value = null;
  try {
    results.value = await getHomeworkResults(lessonId);
    if (view.value === "problems") problems.value = await getHomeworkProblems(lessonId);
  } catch (e) {
    error.value = describeApiError(e, "Не удалось загрузить результаты.");
  }
}
onMounted(load);

async function showProblems() {
  view.value = "problems";
  if (!problems.value) {
    try {
      problems.value = await getHomeworkProblems(lessonId);
    } catch (e) {
      error.value = describeApiError(e);
    }
  }
}

async function openSettings() {
  settingsOpen.value = !settingsOpen.value;
  if (settingsOpen.value && !settings.value) {
    const hw = await getTeacherHomework(lessonId);
    settings.value = hw.settings;
    taskCount.value = hw.tasks.length;
  }
}

async function addTime() {
  try {
    const r = await addTimeToOpenAttempts(lessonId, 10);
    notice.value = r.updated ? `Добавлено 10 минут: ${r.updated} учеников, которые сейчас решают.` : "Сейчас никто не решает с таймером — добавлять некому.";
  } catch (e) {
    error.value = describeApiError(e);
  }
}

const rows = computed<HwResultRow[]>(() => {
  const all = results.value?.rows ?? [];
  switch (filter.value) {
    case "done":
      return all.filter((r) => r.result);
    case "not":
      return all.filter((r) => !r.result);
    case "manual":
      return all.filter((r) => r.state === "manual_pending");
    case "flag":
      return all.filter((r) => r.flags.length);
    default:
      return all;
  }
});

const tabs = computed(() => {
  const sum = results.value?.summary;
  return [
    { id: "all" as const, label: `Все (${sum?.students ?? 0})` },
    { id: "done" as const, label: `Сдали (${sum?.submitted ?? 0})` },
    { id: "not" as const, label: `Не сдали (${sum?.not_submitted ?? 0})` },
    { id: "manual" as const, label: `Проверить вам (${sum?.manual_pending ?? 0})` },
    { id: "flag" as const, label: `Подозрительные (${sum?.flagged ?? 0})` },
  ];
});

function rowMeta(r: HwResultRow): string {
  if (r.state === "not_started") return r.extended_until ? `Не сдано · личный срок до ${formatKz(r.extended_until)}` : "Ещё не сдано";
  if (r.state === "in_progress") return "Решает прямо сейчас";
  const parts = [`Попыток: ${r.attempts_used}`];
  if (r.duration_seconds != null) parts.push(r.duration_seconds < 60 ? `${r.duration_seconds} с` : `${Math.round(r.duration_seconds / 60)} мин`);
  if (r.away_count) parts.push(`уходил(а) со страницы ${r.away_count} раз`);
  if (r.in_progress) parts.push("сейчас решает ещё раз");
  return parts.join(" · ");
}

function gradeClass(r: HwResultRow): string {
  const g = r.result?.grade;
  if (g == null) return "bg-paper-2 text-ink-2";
  return g >= 80 ? "bg-moss/15 text-moss" : g >= 50 ? "bg-amber-100 text-amber-900 dark:bg-amber-400/15 dark:text-amber-200" : "bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400";
}

function problemBar(p: HwProblem): string {
  return p.percent >= 60 ? "bg-red-500" : p.percent >= 40 ? "bg-amber-500" : "bg-moss";
}

/** Spots nobody got wrong are not "problems": the list shows the rest. */
const shownProblems = computed(() => (problems.value ?? []).filter((p) => p.wrong > 0));

function problemTone(p: HwProblem): string {
  return p.percent >= 60 ? "bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400" : p.percent >= 40 ? "bg-amber-100 text-amber-900 dark:bg-amber-400/15 dark:text-amber-200" : "bg-moss/15 text-moss";
}

function correctText(p: HwProblem): string | null {
  if (p.correct.answers) return p.correct.answers.join(" или ");
  if (p.correct.gaps && p.item_label) {
    const n = Number(p.item_label.replace(/\D/g, "")) - 1;
    return p.correct.gaps[n]?.join(" или ") ?? null;
  }
  return null;
}
</script>

<template>
  <PageContainer>
    <div class="mx-auto max-w-5xl space-y-6">
      <BackLink to="/teacher/categories" label="К курсам" />

      <p v-if="error" class="rounded-xl bg-red-50 dark:bg-red-500/10 px-4 py-3 text-red-700 dark:text-red-400" role="alert">
        {{ error }} <button type="button" class="font-semibold underline" @click="load">Повторить</button>
      </p>

      <template v-if="results">
        <header class="space-y-1">
          <h1 class="font-display text-3xl font-semibold text-ink">Домашка: {{ results.lesson.title }}</h1>
          <p class="text-ink-2">
            Срок сдачи: <b>{{ results.settings.deadline ? formatKz(results.settings.deadline) : "без срока" }}</b> · на попытку:
            <b>{{ results.settings.time_limit_minutes ? `${results.settings.time_limit_minutes} мин` : "без ограничения" }}</b>
            <template v-if="results.reveal_at"> · ответы откроются {{ formatKz(results.reveal_at) }}</template>
          </p>
        </header>

        <section class="space-y-3 rounded-2xl border border-line bg-paper p-4">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p class="font-semibold text-ink">Настройки для всего класса</p>
              <p class="text-sm text-ink-3">Можно менять, даже когда ученики уже решают — новое время они увидят сразу.</p>
            </div>
            <div class="flex flex-wrap gap-2">
              <button type="button" class="btn-ghost min-h-11" @click="addTime">+10 минут тем, кто решает</button>
              <button type="button" class="btn-ghost min-h-11 border-2 border-moss text-moss" :aria-expanded="settingsOpen" @click="openSettings">
                {{ settingsOpen ? "Свернуть" : "Изменить срок или время" }}
              </button>
            </div>
          </div>
          <p v-if="notice" class="text-moss" role="status">{{ notice }}</p>
          <HwSettings v-if="settingsOpen && settings" :lesson-id="lessonId" :settings="settings" :task-count="taskCount" @saved="(settings = $event), load()" />
        </section>

        <div class="grid grid-cols-2 gap-3 md:grid-cols-4">
          <div class="rounded-2xl border border-line bg-paper p-4">
            <p class="text-sm text-ink-2">Сдали</p>
            <p class="text-3xl font-bold">{{ results.summary.submitted }} <span class="text-lg text-ink-3">из {{ results.summary.students }}</span></p>
          </div>
          <div class="rounded-2xl border border-line bg-paper p-4">
            <p class="text-sm text-ink-2">Средняя оценка</p>
            <p class="text-3xl font-bold">{{ results.summary.average_grade ?? "—" }}<span v-if="results.summary.average_grade != null" class="text-lg text-ink-3">/100</span></p>
          </div>
          <div class="rounded-2xl border border-line bg-paper p-4">
            <p class="text-sm text-ink-2">Проверить вам</p>
            <p class="text-3xl font-bold">{{ results.summary.manual_pending }}</p>
          </div>
          <div class="rounded-2xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-400/20 dark:bg-amber-400/10">
            <p class="text-sm text-amber-900 dark:text-amber-200">Похоже на списывание</p>
            <p class="text-3xl font-bold text-amber-900 dark:text-amber-200">{{ results.summary.flagged }}</p>
          </div>
        </div>

        <div class="grid max-w-xl grid-cols-2 gap-1.5 rounded-2xl bg-paper-2 p-1.5" role="group" aria-label="Что показать">
          <button
            type="button"
            class="min-h-12 rounded-xl font-bold"
            :class="view === 'students' ? 'bg-paper text-moss shadow-sm' : 'text-ink-2'"
            :aria-pressed="view === 'students'"
            @click="view = 'students'"
          >
            Ученики и оценки
          </button>
          <button
            type="button"
            class="min-h-12 rounded-xl font-bold"
            :class="view === 'problems' ? 'bg-paper text-moss shadow-sm' : 'text-ink-2'"
            :aria-pressed="view === 'problems'"
            @click="showProblems"
          >
            Проблемные места
          </button>
        </div>

        <!-- Students -->
        <template v-if="view === 'students'">
          <div class="flex flex-wrap gap-2">
            <button
              v-for="t in tabs"
              :key="t.id"
              type="button"
              class="min-h-11 rounded-xl px-4 font-semibold"
              :class="filter === t.id ? 'bg-moss text-moss-fg' : 'border border-line bg-paper text-ink'"
              :aria-pressed="filter === t.id"
              @click="filter = t.id"
            >
              {{ t.label }}
            </button>
          </div>

          <p v-if="!rows.length" class="rounded-2xl border-2 border-dashed border-line p-6 text-center text-ink-2">Здесь пока никого.</p>
          <ul class="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-paper">
            <li v-for="r in rows" :key="r.student.id" class="space-y-3 p-4">
              <div class="flex flex-wrap items-center gap-3">
                <div class="min-w-0 flex-1 basis-60">
                  <p class="text-lg font-semibold text-ink">{{ r.student.name }}</p>
                  <p class="text-sm text-ink-3">{{ rowMeta(r) }}</p>
                </div>
                <span v-if="r.state === 'manual_pending'" class="badge bg-amber-100 text-amber-900 dark:bg-amber-400/15 dark:text-amber-200">Ждёт вашей проверки</span>
                <span v-if="r.flags.length" class="badge bg-amber-100 text-amber-900 dark:bg-amber-400/15 dark:text-amber-200">⚑ Возможно, списывал(а)</span>
                <span class="min-w-[5.5rem] rounded-xl px-3 py-2 text-center font-bold" :class="gradeClass(r)">
                  {{ r.result ? (r.result.grade != null ? `${r.result.grade}/100` : "…") : "не сдано" }}
                </span>
                <button type="button" class="btn-ghost min-h-11" :aria-expanded="openId === r.student.id" @click="openId = openId === r.student.id ? null : r.student.id">
                  {{ openId === r.student.id ? "Свернуть" : r.result ? "Подробнее" : "Продлить срок" }}
                </button>
              </div>
              <HwStudentPanel v-if="openId === r.student.id" :lesson-id="lessonId" :row="r" @changed="load" />
            </li>
          </ul>
        </template>

        <!-- Problem spots -->
        <template v-else>
          <p class="text-ink-2">Где ошибается весь класс. Если ошиблась большая часть — тему, вероятно, стоит объяснить ещё раз.</p>
          <p v-if="problems && !problems.length" class="rounded-2xl border-2 border-dashed border-line p-6 text-center text-ink-2">Пока нет сданных работ.</p>
          <p v-else-if="problems && !shownProblems.length" class="rounded-2xl bg-moss/10 p-6 text-center font-medium text-moss">Ошибок нет — все сдавшие решили всё верно.</p>
          <ul v-if="problems" class="space-y-3">
            <li v-for="p in shownProblems" :key="`${p.task_id}-${p.item_label}`" class="space-y-3 rounded-2xl border border-line bg-paper p-4">
              <div class="flex flex-wrap items-center gap-3">
                <span class="min-w-[4.5rem] rounded-xl px-3 py-2 text-center text-xl font-bold" :class="problemTone(p)">{{ p.percent }}%</span>
                <div class="min-w-0 flex-1 basis-72">
                  <p class="font-semibold text-ink">
                    Задание {{ p.task_number }}<template v-if="p.item_label"> · {{ p.item_label }}</template>
                    <template v-if="p.prompt">: {{ p.prompt }}</template>
                  </p>
                  <p class="text-sm text-ink-3">Ошиблись {{ p.wrong }} из {{ p.total }}</p>
                </div>
              </div>
              <div class="h-2.5 overflow-hidden rounded-full bg-paper-2"><div class="h-full rounded-full" :class="problemBar(p)" :style="{ width: `${p.percent}%` }" /></div>
              <p v-if="p.common_wrong" class="text-ink-2">
                Чаще всего отвечали: <b>«{{ p.common_wrong }}»</b> ({{ p.common_wrong_count }})<template v-if="correctText(p)"> — верно: <b class="text-moss">{{ correctText(p) }}</b></template>
              </p>
              <p v-if="p.students.length" class="text-sm text-ink-3">Ошиблись: {{ p.students.join(", ") }}</p>
            </li>
          </ul>
        </template>
      </template>
      <div v-else-if="!error" class="h-40 animate-pulse rounded-2xl bg-paper-2" aria-busy="true" />
    </div>
  </PageContainer>
</template>
