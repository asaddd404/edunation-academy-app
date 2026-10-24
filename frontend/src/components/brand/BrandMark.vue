<script setup lang="ts">
import markUrl from "@/assets/brand/mark.png";

/**
 * The Edunation cap on a white plate. The mark's purple and green are
 * brand colours, not neutral ones: on the dark header (and dark-theme cards)
 * they lose contrast, so the plate goes wherever the mark does.
 */
withDefaults(defineProps<{ size?: number }>(), { size: 32 });
</script>

<template>
  <span
    class="inline-flex shrink-0 items-center justify-center rounded-lg bg-white shadow-sm ring-1 ring-black/5"
    :style="{ width: `${size}px`, height: `${size}px` }"
  >
    <img :src="markUrl" alt="" :width="Math.round(size * 0.74)" :height="Math.round(size * 0.74 * 0.86)" class="object-contain" />
  </span>
</template>
