<script setup lang="ts">
import { Crown } from "@lucide/vue";
import { computed } from "vue";

import RankBadge from "@/components/ui/RankBadge.vue";
import StudentAvatar from "@/components/ui/StudentAvatar.vue";
import { useMediaQuery } from "@/composables/useMediaQuery";

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

/**
 * Top three, arranged 2-1-3 so first place stands in the middle and tallest.
 *
 * Each place has its metal -- gold, silver, bronze -- carried through the
 * avatar ring, its glow, the caption and the step. The steps rise out of the
 * floor in 3-2-1 order so first place lands last; all motion is behind
 * `motion-safe:`, so a reduced-motion setting gets the finished podium.
 */
const props = defineProps<{ entries: PodiumEntry[] }>();

const wide = useMediaQuery("(min-width: 640px)");

interface Metal {
  ring: string;
  glow: string;
  step: string;
  edge: string;
  caption: string;
}

const METALS: Record<number, Metal> = {
  1: {
    ring: "linear-gradient(135deg, #FDE68A, #D9A441 55%, #B4801F)",
    glow: "0 0 0 4px rgba(217, 164, 65, 0.22), 0 12px 32px -6px rgba(217, 164, 65, 0.65)",
    step: "linear-gradient(180deg, rgba(253, 230, 138, 0.55), rgba(217, 164, 65, 0.12))",
    edge: "#D9A441",
    caption: "bg-gold/15 text-gold-dark dark:text-gold-light",
  },
  2: {
    ring: "linear-gradient(135deg, #F8FAFC, #AFB8C1 55%, #8A939C)",
    glow: "0 0 0 4px rgba(175, 184, 193, 0.25), 0 12px 28px -8px rgba(138, 147, 156, 0.6)",
    step: "linear-gradient(180deg, rgba(226, 232, 240, 0.6), rgba(175, 184, 193, 0.12))",
    edge: "#AFB8C1",
    caption: "bg-silver/20 text-silver-dark dark:text-silver-light",
  },
  3: {
    ring: "linear-gradient(135deg, #F0C9A4, #C08457 55%, #9A6438)",
    glow: "0 0 0 4px rgba(192, 132, 87, 0.22), 0 12px 28px -8px rgba(192, 132, 87, 0.6)",
    step: "linear-gradient(180deg, rgba(240, 201, 164, 0.55), rgba(192, 132, 87, 0.12))",
    edge: "#C08457",
    caption: "bg-bronze/15 text-bronze-dark dark:text-bronze-light",
  },
};

// Order on screen, step height, and the stagger that makes 1st land last.
const LAYOUT = [
  { rank: 2, height: "h-20 sm:h-28", delay: 150 },
  { rank: 1, height: "h-28 sm:h-36", delay: 300 },
  { rank: 3, height: "h-14 sm:h-20", delay: 0 },
];

const spots = computed(() =>
  LAYOUT.flatMap((spot) => {
    const entry = props.entries.find((e) => e.rank === spot.rank);
    return entry ? [{ ...spot, entry, metal: METALS[spot.rank] }] : [];
  }),
);

function avatarSize(rank: number): number {
  if (rank === 1) return wide.value ? 76 : 58;
  return wide.value ? 60 : 46;
}
</script>

<template>
  <div class="relative px-1 pt-8">
    <!-- Soft emerald halo behind first place. -->
    <div
      class="pointer-events-none absolute inset-x-0 top-0 mx-auto h-48 max-w-md rounded-full bg-brand-glow/20 blur-3xl dark:bg-brand-glow/10"
      aria-hidden="true"
    />

    <ol class="relative flex items-end justify-center gap-2 sm:gap-5" aria-label="Топ-3">
      <li
        v-for="spot in spots"
        :key="spot.entry.student_id"
        class="flex w-1/3 max-w-[13rem] flex-col items-center"
        :aria-label="`${spot.rank} место: ${spot.entry.last_name} ${spot.entry.first_name}, ${spot.entry.caption}`"
      >
        <div
          class="relative mb-3 motion-safe:animate-pop-in"
          :style="{ animationDelay: `${spot.delay + 350}ms` }"
        >
          <Crown
            v-if="spot.rank === 1"
            :size="wide ? 30 : 24"
            :stroke-width="1.6"
            class="absolute -top-7 left-1/2 -ml-[15px] fill-gold text-gold-dark drop-shadow motion-safe:animate-crown-float sm:-top-8"
            aria-hidden="true"
          />
          <div
            class="rounded-full p-[3px] transition-transform duration-300 hover:scale-105"
            :style="{ background: spot.metal.ring, boxShadow: spot.metal.glow }"
          >
            <div class="rounded-full bg-paper p-[2px]">
              <StudentAvatar
                :student-id="spot.entry.student_id"
                :first-name="spot.entry.first_name"
                :last-name="spot.entry.last_name"
                :has-avatar="spot.entry.has_avatar"
                :size="avatarSize(spot.rank)"
              />
            </div>
          </div>
          <RankBadge :rank="spot.rank" :size="wide ? 30 : 24" class="absolute -bottom-2 left-1/2 -translate-x-1/2" />
        </div>

        <p class="mt-1 flex w-full items-center justify-center gap-1 text-center text-xs font-semibold text-ink sm:text-sm">
          <span class="truncate">{{ spot.entry.last_name }} {{ spot.entry.first_name }}</span>
        </p>
        <span v-if="spot.entry.is_me" class="mt-0.5 rounded-full bg-moss px-1.5 py-px text-[10px] font-semibold text-moss-fg">
          Вы
        </span>
        <span
          class="mb-2 mt-1 rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums sm:text-xs"
          :class="spot.metal.caption"
        >
          {{ spot.entry.caption }}
        </span>

        <div
          class="relative w-full origin-bottom overflow-hidden rounded-t-2xl border-t-[3px] motion-safe:animate-podium-rise"
          :class="[spot.height, spot.entry.is_me ? 'ring-2 ring-inset ring-moss/40' : '']"
          :style="{ background: spot.metal.step, borderColor: spot.metal.edge, animationDelay: `${spot.delay}ms` }"
        >
          <span
            class="absolute inset-x-0 top-2 text-center font-display text-3xl font-bold text-ink/15 sm:text-5xl dark:text-white/15"
            aria-hidden="true"
          >
            {{ spot.rank }}
          </span>
          <!-- One sweep of light across the winner's step. -->
          <span
            v-if="spot.rank === 1"
            class="absolute inset-0 bg-[linear-gradient(110deg,transparent_35%,rgba(255,255,255,0.55)_50%,transparent_65%)] bg-[length:200%_100%] bg-no-repeat motion-safe:animate-shine motion-reduce:hidden"
            aria-hidden="true"
          />
        </div>
      </li>
    </ol>
    <!-- The floor the steps stand on. -->
    <div class="h-1.5 rounded-full bg-gradient-to-r from-transparent via-brand/60 to-transparent dark:via-brand-glow/40" aria-hidden="true" />
  </div>
</template>
