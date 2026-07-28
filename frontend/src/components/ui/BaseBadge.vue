<script setup lang="ts">
withDefaults(defineProps<{ tone?: "neutral" | "success" | "warning" | "danger" }>(), { tone: "neutral" });
</script>

<template>
  <span
    class="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium"
    :class="{
      'bg-fg/10 text-fg/70': tone === 'neutral',
      'bg-green-500/15 text-green-500': tone === 'success',
      'bg-yellow-500/15 text-yellow-500': tone === 'warning',
      'bg-red-500/15 text-red-500': tone === 'danger',
    }"
  >
    <slot />
  </span>
</template>
