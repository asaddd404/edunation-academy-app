<script setup lang="ts">
import { isAxiosError } from "axios";
import { Award, Check, Clock, Flame, Target, Trophy, X, Zap } from "@lucide/vue";
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { getLeaderboard, getLessonLeaderboard, getSectionLeaderboard, listLeaderboardScopes } from "@/api/leaderboard";
import PageContainer from "@/components/layout/PageContainer.vue";
import LeaderboardPodium, { type PodiumEntry } from "@/components/leaderboard/LeaderboardPodium.vue";
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

/** The viewer's own row on whichever board is showing, for the hero card. */
const myStanding = computed(() => {
  if (mode.value === "overall") {
    const me = overall.value?.me;
    return me ? { rank: me.rank, value: `${me.total_xp} XP` } : null;
  }
  const me = testBoard.value?.me;
  return me ? { rank: me.rank, value: `${me.score}% · ${formatDuration(me.duration_seconds)}` } : null;
});

/** Staggers the list's entrance without making a long list wait. */
const stagger = (i: number) => ({ animationDelay: `${Math.min(i, 12) * 35}ms` });

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
    <!-- ── Hero: brand emerald in both themes, white text ─────────────── -->
    <section
      class="relative mb-6 overflow-hidden rounded-3xl bg-gradient-to-br from-brand-deep via-brand to-brand-deep p-5 text-white shadow-lg shadow-brand/20 sm:p-7"
    >
      <div class="pointer-events-none absolute -right-16 -top-20 h-56 w-56 rounded-full bg-brand-glow/20 blur-3xl" aria-hidden="true" />
      <div class="pointer-events-none absolute -bottom-24 left-1/4 h-48 w-48 rounded-full bg-gold/10 blur-3xl" aria-hidden="true" />
      <Trophy
        :size="140"
        :stroke-width="1"
        class="pointer-events-none absolute -bottom-6 -right-4 hidden text-white/[0.07] sm:block"
        aria-hidden="true"
      />

      <div class="relative flex flex-wrap items-start justify-between gap-4">
        <div class="min-w-0">
          <p class="text-xs font-semibold uppercase tracking-[0.18em] text-brand-glow">Рейтинг Edunation</p>
          <h1 class="mt-1 font-display text-2xl font-semibold sm:text-3xl">Тесты и рейтинг</h1>
          <p class="mt-1 max-w-md text-sm text-white/70">{{ periodNote }}</p>
        </div>
        <div
          v-if="myStanding && !loading"
          class="flex items-center gap-3 rounded-2xl bg-white/10 px-4 py-3 ring-1 ring-white/15 backdrop-blur motion-safe:animate-fade-in"
        >
          <span class="flex h-10 w-10 items-center justify-center rounded-xl bg-gold/90 text-brand-deep">
            <Award :size="22" :stroke-width="2" />
          </span>
          <div>
            <p class="text-[11px] uppercase tracking-wide text-white/60">Ваше место</p>
            <p class="text-lg font-bold leading-tight">
              #{{ myStanding.rank }} <span class="text-sm font-medium text-white/75">· {{ myStanding.value }}</span>
            </p>
          </div>
        </div>
      </div>

      <div v-if="!accessDenied" class="relative mt-5 flex flex-wrap items-center gap-2">
        <div class="inline-flex rounded-xl bg-black/15 p-1 ring-1 ring-white/10" role="tablist" aria-label="Вид рейтинга">
          <button
            v-for="m in MODES"
            :key="m.value"
            type="button"
            role="tab"
            class="rounded-lg px-3 py-1.5 text-sm font-medium transition-all duration-200 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60 sm:px-4"
            :class="mode === m.value ? 'bg-white text-brand-deep shadow' : 'text-white/75 hover:bg-white/10 hover:text-white'"
            :aria-selected="mode === m.value"
            @click="setMode(m.value)"
          >
            {{ m.label }}
          </button>
        </div>

        <div v-if="mode === 'overall'" class="inline-flex rounded-xl bg-black/15 p-1 ring-1 ring-white/10">
          <button
            v-for="p in PERIODS"
            :key="p.value"
            type="button"
            class="rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all duration-200 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60 sm:px-3 sm:text-sm"
            :class="period === p.value ? 'bg-white/90 text-brand-deep' : 'text-white/70 hover:bg-white/10 hover:text-white'"
            :aria-pressed="period === p.value"
            @click="period = p.value"
          >
            {{ p.label }}
          </button>
        </div>

        <select
          v-else-if="pickerGroups.length"
          class="w-full rounded-xl border-0 bg-white/95 px-3 py-2 text-sm text-brand-deep shadow-sm ring-1 ring-white/20 focus:outline-none focus:ring-2 focus:ring-brand-glow sm:w-auto sm:min-w-[18rem]"
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
    </section>

    <div v-if="accessDenied" class="card p-4 text-sm">
      <p class="text-ink-2">Рейтинг доступен после одобрения хотя бы одной заявки на курс.</p>
      <router-link class="mt-2 inline-block text-moss underline underline-offset-2 hover:opacity-70" to="/catalog">
        Перейти в каталог курсов
      </router-link>
    </div>

    <template v-else>
      <div v-if="loading" class="space-y-2">
        <div class="mx-auto mb-6 flex h-48 max-w-lg items-end justify-center gap-3">
          <div class="h-20 w-1/3 animate-pulse rounded-t-2xl bg-paper-2" />
          <div class="h-32 w-1/3 animate-pulse rounded-t-2xl bg-paper-2" />
          <div class="h-14 w-1/3 animate-pulse rounded-t-2xl bg-paper-2" />
        </div>
        <div v-for="i in 5" :key="i" class="h-16 w-full animate-pulse rounded-2xl bg-paper-2" />
      </div>

      <p v-else-if="loadError" class="card p-4 text-sm text-clay">{{ loadError }}</p>

      <!-- ── Overall XP board ─────────────────────────────────────────── -->
      <template v-else-if="mode === 'overall' && overall">
        <div v-if="overall.entries.length" class="space-y-6">
          <LeaderboardPodium v-if="overallPodium.length" :entries="overallPodium" />

          <ul v-if="overallRest.length" class="space-y-2">
            <li
              v-for="(entry, i) in overallRest"
              :key="entry.student_id"
              class="group relative flex items-center gap-3 overflow-hidden rounded-2xl border p-3 transition-all duration-200 ease-out hover:-translate-y-0.5 hover:shadow-lg hover:shadow-brand/10 motion-safe:animate-fade-up sm:gap-4 sm:px-4"
              :class="
                entry.is_me
                  ? 'border-moss/50 bg-moss/[0.07] ring-1 ring-moss/30'
                  : 'border-line bg-paper hover:border-moss/40'
              "
              :style="stagger(i)"
            >
              <!-- Top-10 rows carry an emerald edge. -->
              <span
                v-if="entry.rank <= 10"
                class="absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-brand-glow to-brand"
                aria-hidden="true"
              />
              <RankBadge :rank="entry.rank" :size="34" />
              <StudentAvatar
                :student-id="entry.student_id"
                :first-name="entry.first_name"
                :last-name="entry.last_name"
                :has-avatar="entry.has_avatar"
                :size="40"
                class="transition-shadow duration-200 group-hover:ring-2 group-hover:ring-moss/40"
              />
              <div class="min-w-0 flex-1">
                <p class="flex items-center gap-1.5 truncate text-sm font-semibold text-ink">
                  <span class="truncate">{{ fullName(entry) }}</span>
                  <span v-if="entry.is_me" class="shrink-0 rounded-full bg-moss px-1.5 py-px text-[10px] font-semibold text-moss-fg">Вы</span>
                  <span
                    v-else-if="entry.rank <= 10"
                    class="hidden shrink-0 items-center gap-0.5 rounded-full bg-gold/15 px-1.5 py-px text-[10px] font-semibold text-gold-dark dark:text-gold-light sm:inline-flex"
                  >
                    <Award :size="11" /> Топ-10
                  </span>
                </p>
                <p class="mt-0.5 flex items-center gap-3 text-xs text-ink-3">
                  <span class="inline-flex items-center gap-1" :title="`Пройдено тестов: ${entry.tests_passed}`">
                    <Flame :size="13" class="text-orange-500" />
                    {{ entry.tests_passed }} {{ pluralRu(entry.tests_passed, ["тест", "теста", "тестов"]) }}
                  </span>
                  <span class="inline-flex items-center gap-1" :title="`Симуляций ЕНТ: ${entry.simulations_completed}`">
                    <Zap :size="13" class="text-brand-glow" /> {{ entry.simulations_completed }} ЕНТ
                  </span>
                </p>
              </div>
              <span
                class="shrink-0 rounded-full bg-gradient-to-r from-brand to-brand-deep px-3 py-1 text-xs font-bold tabular-nums text-white shadow-sm transition-transform duration-200 group-hover:scale-105"
              >
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

            <!-- Phones: one card per student, nothing to scroll sideways. -->
            <ul class="space-y-2 sm:hidden">
              <li
                v-for="(entry, i) in testBoard.entries"
                :key="entry.student_id"
                class="rounded-2xl border p-3 motion-safe:animate-fade-up"
                :class="entry.is_me ? 'border-moss/50 bg-moss/[0.07]' : 'border-line bg-paper'"
                :style="stagger(i)"
              >
                <div class="flex items-center gap-2.5">
                  <RankBadge :rank="entry.rank" :size="30" />
                  <StudentAvatar
                    :student-id="entry.student_id"
                    :first-name="entry.first_name"
                    :last-name="entry.last_name"
                    :has-avatar="entry.has_avatar"
                    :size="32"
                  />
                  <span class="min-w-0 flex-1 truncate text-sm font-semibold text-ink">{{ fullName(entry) }}</span>
                  <span
                    class="inline-flex shrink-0 items-center gap-0.5 rounded-full px-2 py-0.5 text-[11px] font-bold"
                    :class="entry.passed ? 'bg-green-600/15 text-green-700 dark:text-green-400' : 'bg-red-500/15 text-red-600 dark:text-red-400'"
                  >
                    <component :is="entry.passed ? Check : X" :size="12" :stroke-width="3" />
                    {{ entry.passed ? "PASS" : "FAIL" }}
                  </span>
                </div>
                <div class="mt-2.5 flex items-center gap-2">
                  <div class="h-2 flex-1 overflow-hidden rounded-full bg-paper-2">
                    <div
                      class="h-full rounded-full"
                      :class="entry.passed ? 'bg-gradient-to-r from-green-500 to-emerald-400' : 'bg-gradient-to-r from-red-500 to-orange-400'"
                      :style="{ width: `${entry.score}%` }"
                    />
                  </div>
                  <span class="w-10 text-right text-xs font-semibold tabular-nums text-ink">{{ entry.score }}%</span>
                </div>
                <dl class="mt-2 grid grid-cols-3 gap-1.5 text-center text-xs">
                  <div class="rounded-lg bg-paper-2 py-1.5">
                    <dt class="text-ink-3">Верно</dt>
                    <dd class="font-semibold tabular-nums text-ink">{{ correctLabel(entry) }}</dd>
                  </div>
                  <div class="rounded-lg bg-paper-2 py-1.5">
                    <dt class="text-ink-3">XP</dt>
                    <dd class="font-semibold tabular-nums text-moss">+{{ entry.xp_earned }}</dd>
                  </div>
                  <div class="rounded-lg bg-paper-2 py-1.5">
                    <dt class="text-ink-3">Время</dt>
                    <dd class="font-semibold tabular-nums text-ink">{{ formatDuration(entry.duration_seconds) }}</dd>
                  </div>
                </dl>
              </li>
            </ul>

            <!-- Wider screens: a table. -->
            <div class="hidden overflow-x-auto rounded-2xl border border-line bg-paper shadow-sm sm:block">
              <table class="w-full min-w-[40rem] text-sm">
                <thead class="bg-brand/[0.06] text-left text-[11px] uppercase tracking-wider text-ink-3 dark:bg-white/[0.03]">
                  <tr>
                    <th scope="col" class="px-4 py-3 font-semibold">Ученик</th>
                    <th scope="col" class="px-3 py-3 font-semibold">Статус</th>
                    <th scope="col" class="px-3 py-3 font-semibold"><Target :size="12" class="mr-1 inline" />Точность</th>
                    <th scope="col" class="px-3 py-3 text-right font-semibold">Верно</th>
                    <th scope="col" class="px-3 py-3 text-right font-semibold">XP</th>
                    <th scope="col" class="px-4 py-3 text-right font-semibold"><Clock :size="12" class="mr-1 inline" />Время</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(entry, i) in testBoard.entries"
                    :key="entry.student_id"
                    class="border-t border-line transition-colors duration-150 motion-safe:animate-fade-in"
                    :class="entry.is_me ? 'bg-moss/[0.07]' : 'hover:bg-paper-2/70'"
                    :style="stagger(i)"
                  >
                    <td class="px-4 py-3">
                      <div class="flex items-center gap-3">
                        <RankBadge :rank="entry.rank" :size="30" />
                        <StudentAvatar
                          :student-id="entry.student_id"
                          :first-name="entry.first_name"
                          :last-name="entry.last_name"
                          :has-avatar="entry.has_avatar"
                          :size="32"
                        />
                        <span class="max-w-[14rem] truncate font-medium text-ink">{{ fullName(entry) }}</span>
                        <span v-if="entry.is_me" class="rounded-full bg-moss px-1.5 py-px text-[10px] font-semibold text-moss-fg">Вы</span>
                      </div>
                    </td>
                    <td class="px-3 py-3">
                      <span
                        class="inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-[11px] font-bold"
                        :class="entry.passed ? 'bg-green-600/15 text-green-700 dark:text-green-400' : 'bg-red-500/15 text-red-600 dark:text-red-400'"
                      >
                        <component :is="entry.passed ? Check : X" :size="12" :stroke-width="3" />
                        {{ entry.passed ? "PASS" : "FAIL" }}
                      </span>
                    </td>
                    <td class="px-3 py-3">
                      <div class="flex items-center gap-2">
                        <div
                          class="h-2 w-28 overflow-hidden rounded-full bg-paper-2"
                          role="progressbar"
                          :aria-valuenow="entry.score"
                          aria-valuemin="0"
                          aria-valuemax="100"
                        >
                          <div
                            class="h-full rounded-full"
                            :class="entry.passed ? 'bg-gradient-to-r from-green-500 to-emerald-400' : 'bg-gradient-to-r from-red-500 to-orange-400'"
                            :style="{ width: `${entry.score}%` }"
                          />
                        </div>
                        <span class="tabular-nums text-ink">{{ entry.score }}%</span>
                      </div>
                    </td>
                    <td class="px-3 py-3 text-right tabular-nums text-ink">{{ correctLabel(entry) }}</td>
                    <td class="px-3 py-3 text-right font-bold tabular-nums text-moss">+{{ entry.xp_earned }}</td>
                    <td class="px-4 py-3 text-right tabular-nums text-ink-2">{{ formatDuration(entry.duration_seconds) }}</td>
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
              :to="testBoard.scope === 'lesson' ? `/lessons/${testBoard.scope_id}` : `/sections/${testBoard.scope_id}/test`"
              class="btn-primary"
            >
              Пройти тест первым
            </router-link>
          </div>
        </template>
      </template>

      <!-- The signed-in student's own standing, pinned to the bottom of the
           viewport so it stays visible however long the list is. -->
      <div
        v-if="!loading && (mode === 'overall' ? overall?.me : testBoard?.me)"
        class="sticky bottom-0 z-10 -mx-4 mt-6 px-4 pt-2"
        :style="{ paddingBottom: 'calc(1rem + env(safe-area-inset-bottom, 0px))' }"
      >
        <div
          class="flex items-center gap-3 rounded-2xl bg-gradient-to-r from-brand-deep to-brand p-3 text-sm text-white shadow-xl shadow-brand/30 ring-1 ring-white/10"
        >
          <template v-if="mode === 'overall' && overall?.me">
            <RankBadge :rank="overall.me.rank" :size="32" />
            <StudentAvatar
              :student-id="overall.me.student_id"
              :first-name="overall.me.first_name"
              :last-name="overall.me.last_name"
              :has-avatar="overall.me.has_avatar"
              :size="36"
              class="ring-2 ring-white/30"
            />
            <div class="min-w-0 flex-1">
              <p class="truncate font-semibold">{{ fullName(overall.me) }}</p>
              <p class="text-[11px] text-white/65">Это вы · {{ overall.me.tests_passed }} {{ pluralRu(overall.me.tests_passed, ["тест", "теста", "тестов"]) }}</p>
            </div>
            <span class="shrink-0 rounded-full bg-white px-3 py-1 text-xs font-bold tabular-nums text-brand-deep">
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
              :size="36"
              class="ring-2 ring-white/30"
            />
            <div class="min-w-0 flex-1">
              <p class="truncate font-semibold">{{ fullName(testBoard.me) }}</p>
              <p class="truncate text-[11px] tabular-nums text-white/65">
                {{ testBoard.me.passed ? "PASS" : "FAIL" }} · {{ testBoard.me.score }}% · {{ correctLabel(testBoard.me) }} ·
                {{ formatDuration(testBoard.me.duration_seconds) }}
              </p>
            </div>
            <span class="shrink-0 rounded-full bg-white px-3 py-1 text-xs font-bold tabular-nums text-brand-deep">
              +{{ testBoard.me.xp_earned }} XP
            </span>
          </template>
        </div>
      </div>
    </template>
  </PageContainer>
</template>
