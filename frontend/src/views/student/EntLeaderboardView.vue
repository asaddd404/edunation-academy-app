<script setup lang="ts">
import { onMounted, ref } from "vue";

import { getEntLeaderboard } from "@/api/ent";
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

function medal(rank: number): string | null {
  if (rank === 1) return "🥇";
  if (rank === 2) return "🥈";
  if (rank === 3) return "🥉";
  return null;
}
</script>

<template>
  <div class="mx-auto max-w-2xl space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-semibold">Топ студентов</h1>
      <router-link class="text-sm text-accent hover:underline" to="/ent">← К симулятору</router-link>
    </div>

    <p v-if="loading" class="text-fg/60">Загрузка…</p>

    <template v-else-if="board">
      <div
        v-if="board.me && !board.entries.some((e) => e.is_me)"
        class="rounded-xl border border-accent/40 bg-accent/5 p-4"
      >
        <p class="mb-1 text-xs uppercase tracking-wide text-fg/50">Ваша позиция</p>
        <div class="flex items-center justify-between text-sm">
          <span>#{{ board.me.rank }} · {{ fullName(board.me) }}</span>
          <span class="font-medium">{{ board.me.total_xp }} XP</span>
        </div>
      </div>

      <ul v-if="board.entries.length" class="space-y-2">
        <li
          v-for="entry in board.entries"
          :key="entry.student_id"
          class="flex items-center justify-between rounded-lg border p-3 text-sm"
          :class="entry.is_me ? 'border-accent/50 bg-accent/5' : 'border-fg/10'"
        >
          <div class="flex items-center gap-3">
            <span class="w-8 text-center font-medium text-fg/60">{{ medal(entry.rank) ?? `#${entry.rank}` }}</span>
            <span>{{ fullName(entry) }}</span>
            <BaseBadge v-if="entry.is_me" tone="success">Это вы</BaseBadge>
          </div>
          <div class="flex items-center gap-3 text-fg/60">
            <span>{{ entry.simulations_completed }} попыток</span>
            <span>Лучший: {{ entry.best_score }}</span>
            <span class="font-medium text-fg">{{ entry.total_xp }} XP</span>
          </div>
        </li>
      </ul>
      <p v-else class="text-sm text-fg/60">Пока никто не прошёл ни одной симуляции.</p>
    </template>
  </div>
</template>
