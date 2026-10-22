<script setup lang="ts">
import { isAxiosError } from "axios";
import { Trophy } from "@lucide/vue";
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { getLeaderboard, getLessonLeaderboard, getSectionLeaderboard, listLeaderboardScopes } from "@/api/leaderboard";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import LeaderboardPodium, { type PodiumEntry } from "@/components/leaderboard/LeaderboardPodium.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import RankBadge from "@/components/ui/RankBadge.vue";
import StudentAvatar from "@/components/ui/StudentAvatar.vue";
import type {
  Leaderboard,
  LeaderboardEntry,
  LeaderboardPeriod,
  LeaderboardScopeCategory,
  TestLeaderboard,
  TestLeaderboardEntry,
} from "@/types";
import { formatDuration } from "@/utils/answers";
import { pluralRu } from "@/utils/subjectTheme";

type Mode = "overall" | "section" | "lesson";

const route = useRoute();
const router = useRouter();

const MODES: { value: Mode; label: string }[] = [
  { value: "overall", label: "Общий" },
  { value: "section", label: "По разделу" },
  { value: "lesson", label: "По уроку" },
];

const PERIODS: { value: LeaderboardPeriod; label: string }[] = [
  { value: "week", label: "За неделю" },
  { value: "month", label: "За месяц" },
  { value: "all", label: "За всё время" },
];

// The URL is the state: a lesson page links straight to `?lesson=12`, and a
// shared link opens the same board.
// Keyed on presence, not value: `?lesson=` (no board picked yet) is still
// the lesson tab.
const mode = computed<Mode>(() =>
  route.query.lesson !== undefined ? "lesson" : route.query.section !== undefined ? "section" : "overall",
);
const selectedId = computed(() => Number(route.query.lesson ?? route.query.section) || null);
const period = ref<LeaderboardPeriod>("all");

const overall = ref<Leaderboard | null>(null);
const testBoard = ref<TestLeaderboard | null>(null);
const scopes = ref<LeaderboardScopeCategory[] | null>(null);
const loading = ref(true);
const accessDenied = ref(false);
const loadError = ref("");

/** Options for the lesson/section picker, grouped by course. */
const pickerGroups = computed(() =>
  (scopes.value ?? [])
    .map((category) => ({
      label: category.name,
      options:
        mode.value === "section"
          ? category.sections.filter((s) => s.has_test).map((s) => ({ id: s.id, title: s.title }))
          : category.sections.flatMap((s) => s.lessons.map((l) => ({ id: l.id, title: `${s.title} — ${l.title}` }))),
    }))
    .filter((group) => group.options.length),
);

function setMode(next: Mode) {
  if (next === mode.value) return;
  if (next === "overall") {
    router.replace({ query: {} });
    return;
  }
  // Pick the first board of that kind, so switching tabs never lands on an
  // empty "choose something" screen when there is something to show.
  void ensureScopes().then(() => {
    const first = (scopes.value ?? [])
      .flatMap((c) => c.sections)
      .flatMap((s) => (next === "section" ? (s.has_test ? [s.id] : []) : s.lessons.map((l) => l.id)))[0];
    router.replace({ query: first ? { [next]: String(first) } : { [next]: "" } });
  });
}

function select(id: number) {
  router.replace({ query: { [mode.value]: String(id) } });
}

async function ensureScopes() {
  if (scopes.value === null) scopes.value = await listLeaderboardScopes();
}

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    if (mode.value === "overall") {
      overall.value = await getLeaderboard(20, period.value);
    } else {
      await ensureScopes();
      testBoard.value = selectedId.value
        ? mode.value === "lesson"
          ? await getLessonLeaderboard(selectedId.value)
          : await getSectionLeaderboard(selectedId.value)
        : null;
    }
  } catch (e) {
    if (isAxiosError(e) && e.response?.status === 403 && mode.value === "overall") {
      accessDenied.value = true;
    } else {
      loadError.value = "Не удалось загрузить рейтинг.";
    }
  } finally {
    loading.value = false;
  }
}

watch([mode, selectedId, period], load, { immediate: true });

function fullName(entry: { first_name: string; last_name: string }): string {
  return `${entry.last_name} ${entry.first_name}`.trim();
}

/** The podium needs a full top three to read as one. */
function podiumOf<T extends { rank: number }>(entries: T[]): T[] {
  const top = entries.filter((e) => e.rank <= 3);
  return top.length === 3 ? top : [];
}

const overallPodium = computed<PodiumEntry[]>(() =>
  podiumOf(overall.value?.entries ?? []).map((e) => ({ ...e, caption: `${e.total_xp} XP` })),
);
const overallRest = computed<LeaderboardEntry[]>(() => {
  const entries = overall.value?.entries ?? [];
  return overallPodium.value.length ? entries.filter((e) => e.rank > 3) : entries;
});

const testPodium = computed<PodiumEntry[]>(() =>
  podiumOf(testBoard.value?.entries ?? []).map((e) => ({
    ...e,
    caption: `${e.score}% · ${formatDuration(e.duration_seconds)}`,
  })),
);

function correctLabel(e: TestLeaderboardEntry): string {
  return e.correct_count == null ? "—" : `${e.correct_count} из ${e.question_count}`;
}

const periodNote = computed(() =>
  mode.value !== "overall"
    ? "Лучшая попытка каждого ученика: сначала точность, затем время"
    : period.value === "all"
      ? "XP за ЕНТ-тренажёр и тесты курсов"
      : "XP, заработанные за выбранный период",
);
</script>

<template>
  <PageContainer>
    <PageHeader title="Тесты и рейтинг" :subtitle="periodNote" />

    <div v-if="accessDenied" class="card p-4 text-sm">
      <p class="text-ink-2">Рейтинг доступен после одобрения хотя бы одной заявки на курс.</p>
      <router-link class="mt-2 inline-block text-moss underline underline-offset-2 hover:opacity-70" to="/catalog">
        Перейти в каталог курсов
      </router-link>
    </div>

    <template v-else>
      <div class="mb-6 flex flex-wrap items-center gap-3">
        <div class="inline-flex rounded-xl border border-line bg-paper-2 p-1" role="tablist" aria-label="Вид рейтинга">
          <button
            v-for="m in MODES"
            :key="m.value"
            type="button"
            role="tab"
            class="rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200 ease-out sm:px-4"
            :class="mode === m.value ? 'bg-paper text-ink shadow-sm' : 'text-ink-2 hover:text-ink'"
            :aria-selected="mode === m.value"
            @click="setMode(m.value)"
          >
            {{ m.label }}
          </button>
        </div>

        <div v-if="mode === 'overall'" class="inline-flex rounded-xl border border-line bg-paper-2 p-1">
          <button
            v-for="p in PERIODS"
            :key="p.value"
            type="button"
            class="rounded-lg px-3 py-2 text-xs font-medium transition-all duration-200 ease-out sm:text-sm"
            :class="period === p.value ? 'bg-paper text-ink shadow-sm' : 'text-ink-2 hover:text-ink'"
            :aria-pressed="period === p.value"
            @click="period = p.value"
          >
            {{ p.label }}
          </button>
        </div>

        <select
          v-else-if="pickerGroups.length"
          class="input w-full sm:w-auto sm:min-w-[18rem]"
          :aria-label="mode === 'lesson' ? 'Урок' : 'Раздел'"
          :value="selectedId ?? ''"
          @change="select(Number(($event.target as HTMLSelectElement).value))"
        >
          <option value="" disabled>{{ mode === "lesson" ? "Выберите урок" : "Выберите раздел" }}</option>
          <optgroup v-for="group in pickerGroups" :key="group.label" :label="group.label">
            <option v-for="opt in group.options" :key="opt.id" :value="opt.id">{{ opt.title }}</option>
          </optgroup>
        </select>
      </div>

      <div v-if="loading" class="space-y-2">
        <div v-for="i in 6" :key="i" class="h-14 w-full animate-pulse rounded-xl bg-paper-2" />
      </div>

      <p v-else-if="loadError" class="card p-4 text-sm text-clay">{{ loadError }}</p>

      <!-- ── Overall XP board ─────────────────────────────────────────── -->
      <template v-else-if="mode === 'overall' && overall">
        <div v-if="overall.entries.length" class="space-y-6">
          <LeaderboardPodium v-if="overallPodium.length" :entries="overallPodium" />

          <ul v-if="overallRest.length" class="space-y-2">
            <li
              v-for="entry in overallRest"
              :key="entry.student_id"
              class="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-xl border p-3 text-sm transition-all duration-200 ease-out hover:shadow-sm sm:flex-nowrap"
              :class="entry.is_me ? 'border-moss/40 bg-moss/5' : 'card hover:border-line-strong'"
            >
              <RankBadge :rank="entry.rank" :size="32" />
              <StudentAvatar
                :student-id="entry.student_id"
                :first-name="entry.first_name"
                :last-name="entry.last_name"
                :has-avatar="entry.has_avatar"
                :size="34"
              />
              <span class="min-w-0 flex-1 truncate text-ink">{{ fullName(entry) }}</span>
              <BaseBadge v-if="entry.is_me" tone="success">Это вы</BaseBadge>
              <!-- Secondary stats are the first thing to go on a narrow
                   screen: rank, name and XP are what the list is read for. -->
              <span class="hidden shrink-0 text-xs text-ink-3 md:inline">
                {{ entry.tests_passed }} {{ pluralRu(entry.tests_passed, ["тест", "теста", "тестов"]) }} ·
                {{ entry.simulations_completed }} ЕНТ
              </span>
              <span class="ml-auto shrink-0 rounded-full bg-moss px-2.5 py-1 text-xs font-semibold text-moss-fg sm:ml-0">
                {{ entry.total_xp }} XP
              </span>
            </li>
          </ul>
        </div>

        <div v-else class="card flex flex-col items-center gap-3 px-6 py-12 text-center">
          <span class="flex h-14 w-14 items-center justify-center rounded-full bg-moss/15 text-moss">
            <Trophy :size="28" :stroke-width="1.6" />
          </span>
          <p class="font-medium text-ink">
            {{ period === "all" ? "Пока никто не заработал XP" : "За этот период XP ещё никто не заработал" }}
          </p>
          <p class="max-w-xs text-sm text-ink-2">Пройдите тест урока или пробную симуляцию ЕНТ — и станьте первым.</p>
        </div>
      </template>

      <!-- ── Per-lesson / per-section board ───────────────────────────── -->
      <template v-else-if="mode !== 'overall'">
        <p v-if="!pickerGroups.length" class="card p-4 text-sm text-ink-2">
          В ваших курсах пока нет {{ mode === "lesson" ? "уроков с тестами" : "разделов с итоговым тестом" }}.
        </p>

        <template v-else-if="testBoard">
          <div v-if="testBoard.entries.length" class="space-y-6">
            <LeaderboardPodium v-if="testPodium.length" :entries="testPodium" />

            <div class="overflow-x-auto rounded-xl border border-line">
              <table class="w-full min-w-[42rem] text-sm">
                <thead class="bg-paper-2 text-left text-xs uppercase tracking-wide text-ink-3">
                  <tr>
                    <th scope="col" class="px-3 py-2.5 font-medium">Ученик</th>
                    <th scope="col" class="px-3 py-2.5 font-medium">Статус</th>
                    <th scope="col" class="px-3 py-2.5 font-medium">Точность</th>
                    <th scope="col" class="px-3 py-2.5 text-right font-medium">Верно</th>
                    <th scope="col" class="px-3 py-2.5 text-right font-medium">XP</th>
                    <th scope="col" class="px-3 py-2.5 text-right font-medium">Время</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="entry in testBoard.entries"
                    :key="entry.student_id"
                    class="border-t border-line"
                    :class="entry.is_me ? 'bg-moss/5' : ''"
                  >
                    <td class="px-3 py-2.5">
                      <div class="flex items-center gap-2.5">
                        <RankBadge :rank="entry.rank" :size="30" />
                        <StudentAvatar
                          :student-id="entry.student_id"
                          :first-name="entry.first_name"
                          :last-name="entry.last_name"
                          :has-avatar="entry.has_avatar"
                          :size="30"
                        />
                        <span class="max-w-[12rem] truncate text-ink">{{ fullName(entry) }}</span>
                        <BaseBadge v-if="entry.is_me" tone="success">Вы</BaseBadge>
                      </div>
                    </td>
                    <td class="px-3 py-2.5">
                      <BaseBadge :tone="entry.passed ? 'success' : 'danger'">{{ entry.passed ? "PASS" : "FAIL" }}</BaseBadge>
                    </td>
                    <td class="px-3 py-2.5">
                      <div class="flex items-center gap-2">
                        <div
                          class="h-2 w-24 overflow-hidden rounded-full bg-paper-2"
                          role="progressbar"
                          :aria-valuenow="entry.score"
                          aria-valuemin="0"
                          aria-valuemax="100"
                        >
                          <div
                            class="h-full rounded-full"
                            :class="entry.passed ? 'bg-green-600 dark:bg-green-500' : 'bg-red-500 dark:bg-red-400'"
                            :style="{ width: `${entry.score}%` }"
                          />
                        </div>
                        <span class="tabular-nums text-ink">{{ entry.score }}%</span>
                      </div>
                    </td>
                    <td class="px-3 py-2.5 text-right tabular-nums text-ink">{{ correctLabel(entry) }}</td>
                    <td class="px-3 py-2.5 text-right font-semibold tabular-nums text-moss">+{{ entry.xp_earned }}</td>
                    <td class="px-3 py-2.5 text-right tabular-nums text-ink-2">{{ formatDuration(entry.duration_seconds) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-else class="card flex flex-col items-center gap-3 px-6 py-12 text-center">
            <span class="flex h-14 w-14 items-center justify-center rounded-full bg-moss/15 text-moss">
              <Trophy :size="28" :stroke-width="1.6" />
            </span>
            <p class="font-medium text-ink">«{{ testBoard.title }}»: попыток ещё не было</p>
            <router-link
              v-if="testBoard.scope === 'lesson'"
              :to="`/lessons/${testBoard.scope_id}`"
              class="btn-primary"
            >
              Пройти тест
            </router-link>
            <router-link v-else :to="`/sections/${testBoard.scope_id}/test`" class="btn-primary">Пройти тест</router-link>
          </div>
        </template>
      </template>

      <!-- The signed-in student's own standing, pinned to the bottom of the
           viewport so it stays visible however long the list is. -->
      <div
        v-if="!loading && (mode === 'overall' ? overall?.me : testBoard?.me)"
        class="sticky bottom-0 z-10 -mx-4 mt-4 px-4 pt-2"
        :style="{ paddingBottom: 'calc(1rem + env(safe-area-inset-bottom, 0px))' }"
      >
        <div
          class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-moss/40 bg-paper/95 p-3 text-sm shadow-lg backdrop-blur"
        >
          <template v-if="mode === 'overall' && overall?.me">
            <RankBadge :rank="overall.me.rank" :size="32" />
            <StudentAvatar
              :student-id="overall.me.student_id"
              :first-name="overall.me.first_name"
              :last-name="overall.me.last_name"
              :has-avatar="overall.me.has_avatar"
              :size="34"
            />
            <span class="min-w-0 flex-1 truncate text-ink">{{ fullName(overall.me) }}</span>
            <BaseBadge tone="success">Это вы</BaseBadge>
            <span class="shrink-0 rounded-full bg-moss px-2.5 py-1 text-xs font-semibold text-moss-fg">
              {{ overall.me.total_xp }} XP
            </span>
          </template>
          <template v-else-if="testBoard?.me">
            <RankBadge :rank="testBoard.me.rank" :size="32" />
            <StudentAvatar
              :student-id="testBoard.me.student_id"
              :first-name="testBoard.me.first_name"
              :last-name="testBoard.me.last_name"
              :has-avatar="testBoard.me.has_avatar"
              :size="34"
            />
            <span class="min-w-0 flex-1 truncate text-ink">{{ fullName(testBoard.me) }}</span>
            <BaseBadge :tone="testBoard.me.passed ? 'success' : 'danger'">{{ testBoard.me.passed ? "PASS" : "FAIL" }}</BaseBadge>
            <!-- Dropped on a phone so the name keeps its room; the row in
                 the table above carries the same figures. -->
            <span class="hidden shrink-0 tabular-nums text-ink-2 sm:inline">
              {{ testBoard.me.score }}% · {{ correctLabel(testBoard.me) }} · {{ formatDuration(testBoard.me.duration_seconds) }}
            </span>
            <span class="shrink-0 rounded-full bg-moss px-2.5 py-1 text-xs font-semibold text-moss-fg">
              +{{ testBoard.me.xp_earned }} XP
            </span>
          </template>
        </div>
      </div>
    </template>
  </PageContainer>
</template>
