<script setup lang="ts">
import { Crown, Trophy } from "@lucide/vue";
import { computed, ref, watch } from "vue";

import { getEntLeaderboard } from "@/api/ent";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import BackLink from "@/components/ui/BackLink.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import RankBadge from "@/components/ui/RankBadge.vue";
import StudentAvatar from "@/components/ui/StudentAvatar.vue";
import type { EntLeaderboard, EntLeaderboardEntry, LeaderboardPeriod } from "@/types";
import { pluralRu } from "@/utils/subjectTheme";

const board = ref<EntLeaderboard | null>(null);
const loading = ref(true);
const period = ref<LeaderboardPeriod>("all");

const PERIODS: { value: LeaderboardPeriod; label: string }[] = [
  { value: "week", label: "За неделю" },
  { value: "month", label: "За месяц" },
  { value: "all", label: "За всё время" },
];

async function load() {
  loading.value = true;
  try {
    board.value = await getEntLeaderboard(20, period.value);
  } finally {
    loading.value = false;
  }
}

watch(period, load, { immediate: true });

function fullName(entry: { first_name: string; last_name: string }): string {
  return `${entry.last_name} ${entry.first_name}`.trim();
}

/** Top three arranged 2-1-3 with descending block heights, so the podium
 * reads as a podium rather than as the first three rows of the list. */
const podium = computed<{ entry: EntLeaderboardEntry; height: string; accent: string }[]>(() => {
  const byRank = (rank: number) => board.value?.entries.find((e) => e.rank === rank);
  const layout = [
    { rank: 2, height: "h-16", accent: "border-slate-300 dark:border-slate-400/60" },
    { rank: 1, height: "h-24", accent: "border-amber-400/60" },
    { rank: 3, height: "h-11", accent: "border-amber-700/50" },
  ];
  const spots = [];
  for (const { rank, height, accent } of layout) {
    const entry = byRank(rank);
    if (entry) spots.push({ entry, height, accent });
  }
  return spots;
});

/** The podium needs a full top three to read as one; a short period can have
 * fewer entrants than that. */
const podiumShown = computed(() => podium.value.length >= 3);

/** Everyone the podium is not already showing. When there is no podium the
 * list has to carry all of them -- otherwise a week with one or two entrants
 * renders as a completely empty board. */
const restEntries = computed(() => {
  const entries = board.value?.entries ?? [];
  return podiumShown.value ? entries.filter((e) => e.rank > 3) : entries;
});

const meOutsideList = computed(() => {
  const me = board.value?.me;
  return me && !board.value?.entries.some((e) => e.is_me) ? me : null;
});

const periodNote = computed(() =>
  period.value === "all" ? "Всего заработано XP" : "XP, заработанные за выбранный период",
);
</script>

<template>
  <PageContainer>
    <PageHeader title="Топ студентов" :subtitle="periodNote">
      <template #actions>
        <BackLink to="/ent" label="К тренажёру" />
      </template>
    </PageHeader>

    <!-- Period tabs -->
    <div class="mb-6 inline-flex rounded-xl border border-line bg-paper-2 p-1">
      <button
        v-for="p in PERIODS"
        :key="p.value"
        type="button"
        class="rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200 ease-out sm:px-4"
        :class="period === p.value ? 'bg-paper text-ink shadow-sm' : 'text-ink-2 hover:text-ink'"
        :aria-pressed="period === p.value"
        @click="period = p.value"
      >
        {{ p.label }}
      </button>
    </div>

    <div v-if="loading" class="space-y-2">
      <div v-for="i in 6" :key="i" class="h-14 w-full animate-pulse rounded-xl bg-paper-2" />
    </div>

    <template v-else-if="board">
      <div class="space-y-6">
        <template v-if="board.entries.length">
          <!-- Podium: 2-1-3 so first place stands in the middle and tallest. -->
          <div v-if="podiumShown" class="flex items-end justify-center gap-2 sm:gap-4">
            <div
              v-for="spot in podium"
              :key="spot.entry.student_id"
              class="flex w-1/3 max-w-[12rem] flex-col items-center"
            >
              <Crown
                v-if="spot.entry.rank === 1"
                :size="20"
                :stroke-width="1.8"
                class="mb-1 text-amber-500"
              />
              <div class="relative">
                <StudentAvatar
                  :student-id="spot.entry.student_id"
                  :first-name="spot.entry.first_name"
                  :last-name="spot.entry.last_name"
                  :has-avatar="spot.entry.has_avatar"
                  :size="56"
                  class="ring-2"
                  :class="spot.accent.replace(/border-/g, 'ring-')"
                />
                <RankBadge :rank="spot.entry.rank" :size="26" class="absolute -bottom-1 -right-1" />
              </div>

              <p class="mt-2 w-full truncate text-center text-xs font-medium text-ink sm:text-sm">
                {{ fullName(spot.entry) }}
              </p>
              <p class="mb-2 text-[11px] text-ink-3">{{ spot.entry.total_xp }} XP</p>

              <div
                class="w-full rounded-t-xl border border-b-0 transition-all duration-500 ease-out"
                :class="[spot.height, spot.accent, spot.entry.is_me ? 'bg-moss/15' : 'bg-paper-2']"
              />
            </div>
          </div>

          <ul v-if="restEntries.length" class="space-y-2">
            <li
              v-for="entry in restEntries"
              :key="entry.student_id"
              class="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-xl border p-3 text-sm transition-all duration-200 ease-out hover:shadow-sm sm:flex-nowrap"
              :class="
                entry.is_me
                  ? 'border-moss/40 bg-moss/5'
                  : entry.rank <= 10
                    ? 'card border-moss/20 hover:border-moss/40'
                    : 'card hover:border-line-strong'
              "
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
              <span
                v-else-if="entry.rank <= 10"
                class="shrink-0 rounded-full bg-moss/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-moss"
              >
                Топ-10
              </span>
              <!-- Secondary stats are the first thing to go on a narrow
                   screen: rank, name and XP are what the list is read for. -->
              <span class="hidden shrink-0 text-xs text-ink-3 md:inline">
                {{ entry.simulations_completed }}
                {{ pluralRu(entry.simulations_completed, ["попытка", "попытки", "попыток"]) }} · лучший
                {{ entry.best_score }}
              </span>
              <span class="ml-auto shrink-0 rounded-full bg-moss px-2.5 py-1 text-xs font-semibold text-moss-fg sm:ml-0">
                {{ entry.total_xp }} XP
              </span>
            </li>
          </ul>
        </template>

        <div v-else class="card flex flex-col items-center gap-3 px-6 py-12 text-center">
          <span class="flex h-14 w-14 items-center justify-center rounded-full bg-moss/15 text-moss">
            <Trophy :size="28" :stroke-width="1.6" />
          </span>
          <p class="font-medium text-ink">
            {{ period === "all" ? "Пока никто не прошёл ни одной симуляции" : "За этот период попыток ещё не было" }}
          </p>
          <p class="max-w-xs text-sm text-ink-2">Станьте первым — начните пробную симуляцию ЕНТ.</p>
          <router-link to="/ent" class="btn-primary">Начать симуляцию</router-link>
        </div>
      </div>

      <!-- Sticks to the bottom of the viewport so a student outside the top 20
           can always see where they stand while scrolling the list. -->
      <div v-if="meOutsideList" class="sticky bottom-0 z-10 -mx-4 mt-4 px-4 pb-4 pt-2">
        <div
          class="flex items-center gap-3 rounded-xl border border-moss/40 bg-paper/95 p-3 text-sm shadow-lg backdrop-blur"
        >
          <RankBadge :rank="meOutsideList.rank" :size="32" />
          <StudentAvatar
            :student-id="meOutsideList.student_id"
            :first-name="meOutsideList.first_name"
            :last-name="meOutsideList.last_name"
            :has-avatar="meOutsideList.has_avatar"
            :size="34"
          />
          <span class="min-w-0 flex-1 truncate text-ink">{{ fullName(meOutsideList) }}</span>
          <BaseBadge tone="success">Это вы</BaseBadge>
          <span class="shrink-0 rounded-full bg-moss px-2.5 py-1 text-xs font-semibold text-moss-fg">
            {{ meOutsideList.total_xp }} XP
          </span>
        </div>
      </div>
    </template>
  </PageContainer>
</template>
