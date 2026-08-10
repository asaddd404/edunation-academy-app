<script setup lang="ts">
withDefaults(defineProps<{ tone?: "neutral" | "success" | "warning" | "danger" }>(), { tone: "neutral" });
</script>

<template>
  <span
    class="badge"
    :class="{
      'bg-paper-2 text-ink-2': tone === 'neutral',
      'bg-moss/15 text-moss': tone === 'success',
      'bg-marigold/20 text-ink': tone === 'warning',
      'bg-clay/15 text-clay': tone === 'danger',
    }"
  >
    <slot />
  </span>
</template>
