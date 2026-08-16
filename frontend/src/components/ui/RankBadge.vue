<script setup lang="ts">
import { computed, useId } from "vue";

/**
 * Leaderboard rank marker, drawn rather than typed as an emoji.
 *
 * Emoji medals are rendered by the OS font, so they look different on every
 * machine (and Windows draws flag/medal glyphs inconsistently) -- these are
 * SVG, so the podium looks the same everywhere and can use the app's own
 * palette. Three tiers are distinguished: the top three get a metallic medal,
 * ranks 4-10 get a teal shield marking them as "топ-10", everyone else gets a
 * plain number.
 */
const props = withDefaults(defineProps<{ rank: number; size?: number }>(), { size: 36 });

// Gradient ids must be unique per instance: several badges share a page and
// duplicate ids would make every medal adopt the first one's colours.
const uid = useId();

export type RankTier = "medal" | "top10" | "plain";

const tier = computed<RankTier>(() => {
  if (props.rank <= 3) return "medal";
  if (props.rank <= 10) return "top10";
  return "plain";
});

const METAL: Record<number, { from: string; to: string; ring: string; ink: string }> = {
  1: { from: "#FDE68A", to: "#D9A441", ring: "#B4801F", ink: "#5A3B06" },
  2: { from: "#F1F5F9", to: "#AFB8C1", ring: "#8A939C", ink: "#3F464D" },
  3: { from: "#F0C9A4", to: "#C08457", ring: "#9A6438", ink: "#4E2F16" },
};

const metal = computed(() => METAL[props.rank] ?? METAL[3]);
</script>

<template>
  <span
    class="relative inline-flex shrink-0 items-center justify-center"
    :style="{ width: `${size}px`, height: `${size}px` }"
    :aria-label="`Место ${rank}`"
  >
    <!-- Top three: metallic medal with a ribbon notch. -->
    <svg v-if="tier === 'medal'" viewBox="0 0 40 40" class="h-full w-full">
      <defs>
        <linearGradient :id="`medal-${uid}`" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" :stop-color="metal.from" />
          <stop offset="100%" :stop-color="metal.to" />
        </linearGradient>
      </defs>
      <path :d="'M13 3 L20 14 L27 3'" :stroke="metal.ring" stroke-width="3.5" fill="none" stroke-linecap="round" />
      <circle cx="20" cy="24" r="13" :fill="`url(#medal-${uid})`" :stroke="metal.ring" stroke-width="1.5" />
      <circle cx="20" cy="24" r="9.5" fill="none" :stroke="metal.ring" stroke-width="0.75" opacity="0.5" />
      <text
        x="20"
        y="24"
        text-anchor="middle"
        dominant-baseline="central"
        font-size="11"
        font-weight="700"
        :fill="metal.ink"
      >
        {{ rank }}
      </text>
    </svg>

    <!-- Ranks 4-10: a teal shield, clearly a tier below the medals but still
         visibly "marked" against the plain numbers underneath. -->
    <svg v-else-if="tier === 'top10'" viewBox="0 0 40 40" class="h-full w-full">
      <path
        d="M20 3.5 L33 8.5 V20 C33 28 27 33.5 20 36.5 C13 33.5 7 28 7 20 V8.5 Z"
        class="fill-moss/15 stroke-moss/60"
        stroke-width="1.5"
      />
      <text
        x="20"
        y="20.5"
        text-anchor="middle"
        dominant-baseline="central"
        font-size="13"
        font-weight="700"
        class="fill-moss"
      >
        {{ rank }}
      </text>
    </svg>

    <span v-else class="text-xs font-semibold tabular-nums text-ink-3">{{ rank }}</span>
  </span>
</template>
