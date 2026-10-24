<script setup lang="ts">
import logoUrl from "@/assets/brand/logo.png";
import wordmarkWhiteUrl from "@/assets/brand/wordmark-white.png";
import BrandMark from "@/components/brand/BrandMark.vue";

/**
 * The full logo for light surfaces. The client's file has a navy wordmark,
 * which disappears on dark backgrounds, so dark mode swaps it for the plated
 * mark plus a white cut of the same wordmark.
 */
withDefaults(defineProps<{ height?: number }>(), { height: 48 });
</script>

<template>
  <span class="inline-flex items-center" role="img" aria-label="Edunation Academy">
    <img :src="logoUrl" alt="" :style="{ height: `${height}px` }" class="w-auto dark:hidden" />
    <span class="hidden items-center gap-3 dark:inline-flex">
      <BrandMark :size="height" />
      <img :src="wordmarkWhiteUrl" alt="" :style="{ height: `${Math.round(height * 0.62)}px` }" class="w-auto" />
    </span>
  </span>
</template>
