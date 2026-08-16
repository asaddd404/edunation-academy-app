<script setup lang="ts">
import { computed } from "vue";

import { activityLevel, formatActivityDuration } from "@/utils/activity";

const props = defineProps<{ totalSeconds: number }>();

const level = computed(() => activityLevel(props.totalSeconds));

// Fixed traffic-light semantics, independent of the app's brand accent --
// these colors carry meaning (low/medium/high activity), not just style.
// Drawn as a dot rather than a coloured-circle emoji: the emoji is rendered
// by the OS font, so its size and hue drifted away from the label beside it.
const DOT_TONE: Record<string, string> = {
  low: "bg-red-500",
  medium: "bg-amber-500",
  high: "bg-emerald-500",
};
const TEXT_TONE: Record<string, string> = {
  low: "text-red-600 dark:text-red-500",
  medium: "text-amber-600 dark:text-amber-500",
  high: "text-green-700 dark:text-green-500",
};

const LEVEL_LABEL: Record<string, string> = {
  low: "Низкая активность",
  medium: "Средняя активность",
  high: "Высокая активность",
};
</script>

<template>
  <span class="badge bg-paper-2" :class="TEXT_TONE[level]" :title="LEVEL_LABEL[level]">
    <span class="h-2 w-2 shrink-0 rounded-full" :class="DOT_TONE[level]" aria-hidden="true" />
    {{ formatActivityDuration(totalSeconds) }}
  </span>
</template>
