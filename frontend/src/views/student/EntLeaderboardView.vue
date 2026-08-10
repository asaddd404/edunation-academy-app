<script setup lang="ts">
import { onMounted, ref } from "vue";

import { getEntLeaderboard } from "@/api/ent";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import type { EntLeaderboard } from "@/types";

const board = ref<EntLeaderboard | null>(null);
const loading = ref(true);

async function load() {
  loading.value = true;
  board.value = await getEntLeaderboard(20);
  loading.value = false;
}

onMounted(load);

function fullName(entry: { first_name: string; last_name: string }): string {
  return `${entry.last_name} ${entry.first_name}`.trim();
}
</script>

<template>
  <PageContainer>
    <PageHeader title="Топ студентов">
      <template #actions>
        <router-link class="text-sm text-moss underline underline-offset-2 hover:opacity-70" to="/ent">
          ← К симулятору
        </router-link>
      </template>
    </PageHeader>

    <div v-if="loading" class="space-y-2">
      <div v-for="i in 6" :key="i" class="h-14 w-full animate-pulse rounded-xl bg-paper-2"></div>
    </div>

    <template v-else-if="board">
      <div class="space-y-6">
        <div
          v-if="board.me && !board.entries.some((e) => e.is_me)"
          class="rounded-2xl border border-moss/40 bg-moss/5 p-4"
        >
          <p class="mb-1 text-xs uppercase tracking-wide text-ink-3">Ваша позиция</p>
          <div class="flex items-center justify-between text-sm">
            <span class="text-ink">#{{ board.me.rank }} · {{ fullName(board.me) }}</span>
            <span class="rounded-full bg-moss px-2.5 py-1 text-xs font-semibold text-moss-fg">{{ board.me.total_xp }} XP</span>
          </div>
        </div>

        <ul v-if="board.entries.length" class="space-y-2">
          <li
            v-for="entry in board.entries"
            :key="entry.student_id"
            class="flex items-center justify-between rounded-xl border p-3 text-sm transition-colors hover:border-line-strong"
            :class="entry.is_me ? 'bg-moss/5 border-moss/40' : 'card'"
          >
            <div class="flex items-center gap-3">
              <span
                class="w-8 shrink-0 text-center font-medium"
                :class="entry.rank <= 3 ? 'text-ink' : 'text-ink-2'"
              >
                #{{ entry.rank }}
              </span>
              <span class="text-ink">{{ fullName(entry) }}</span>
              <BaseBadge v-if="entry.is_me" tone="success">Это вы</BaseBadge>
            </div>
            <div class="flex items-center gap-3 text-ink-2">
              <span>{{ entry.simulations_completed }} попыток</span>
              <span>Лучший: {{ entry.best_score }}</span>
              <span class="rounded-full bg-moss px-2.5 py-1 text-xs font-semibold text-moss-fg">{{ entry.total_xp }} XP</span>
            </div>
          </li>
        </ul>
        <div v-else class="card flex flex-col items-center gap-3 px-6 py-12 text-center">
          <div class="flex h-14 w-14 items-center justify-center rounded-full bg-moss/15 text-2xl">🏆</div>
          <p class="font-medium text-ink">Пока никто не прошёл ни одной симуляции</p>
          <p class="max-w-xs text-sm text-ink-2">Станьте первым — начните пробную симуляцию ЕНТ.</p>
          <router-link to="/ent" class="btn-primary">Начать симуляцию</router-link>
        </div>
      </div>
    </template>
  </PageContainer>
</template>
