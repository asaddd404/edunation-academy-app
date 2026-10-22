<script setup lang="ts">
import { Crown } from "@lucide/vue";
import { computed } from "vue";

import RankBadge from "@/components/ui/RankBadge.vue";
import StudentAvatar from "@/components/ui/StudentAvatar.vue";

export interface PodiumEntry {
  rank: number;
  student_id: number;
  first_name: string;
  last_name: string;
  has_avatar: boolean;
  is_me: boolean;
  /** The figure under the name: "540 XP", "100% · 02:13". */
  caption: string;
}

/** Top three arranged 2-1-3 with descending block heights, so the podium
 * reads as a podium rather than as the first three rows of the list. */
const props = defineProps<{ entries: PodiumEntry[] }>();

const LAYOUT = [
  { rank: 2, height: "h-16", accent: "border-slate-300 dark:border-slate-400/60", ring: "ring-slate-300 dark:ring-slate-400/60" },
  { rank: 1, height: "h-24", accent: "border-amber-400/60", ring: "ring-amber-400/60" },
  { rank: 3, height: "h-11", accent: "border-amber-700/50", ring: "ring-amber-700/50" },
];

const spots = computed(() =>
  LAYOUT.flatMap((spot) => {
    const entry = props.entries.find((e) => e.rank === spot.rank);
    return entry ? [{ ...spot, entry }] : [];
  }),
);
</script>

<template>
  <div class="flex items-end justify-center gap-2 sm:gap-4">
    <div v-for="spot in spots" :key="spot.entry.student_id" class="flex w-1/3 max-w-[12rem] flex-col items-center">
      <Crown v-if="spot.entry.rank === 1" :size="20" :stroke-width="1.8" class="mb-1 text-amber-500" />
      <div class="relative">
        <StudentAvatar
          :student-id="spot.entry.student_id"
          :first-name="spot.entry.first_name"
          :last-name="spot.entry.last_name"
          :has-avatar="spot.entry.has_avatar"
          :size="56"
          class="ring-2"
          :class="spot.ring"
        />
        <RankBadge :rank="spot.entry.rank" :size="26" class="absolute -bottom-1 -right-1" />
      </div>
      <p class="mt-2 w-full truncate text-center text-xs font-medium text-ink sm:text-sm">
        {{ spot.entry.last_name }} {{ spot.entry.first_name }}
      </p>
      <p class="mb-2 text-[11px] tabular-nums text-ink-3">{{ spot.entry.caption }}</p>
      <div
        class="w-full rounded-t-xl border border-b-0 transition-all duration-500 ease-out"
        :class="[spot.height, spot.accent, spot.entry.is_me ? 'bg-moss/15' : 'bg-paper-2']"
      />
    </div>
  </div>
</template>
