<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>();
</script>

<template>
  <div class="mb-6 flex flex-wrap items-start justify-between gap-3 border-b border-line pb-4">
    <div class="min-w-0">
      <h1 class="font-display text-display-lg text-ink">{{ title }}</h1>
      <p v-if="subtitle || $slots.subtitle" class="mt-1 text-caption text-ink-3">
        <slot name="subtitle">{{ subtitle }}</slot>
      </p>
    </div>
    <div v-if="$slots.actions" class="flex shrink-0 flex-wrap items-center gap-2">
      <slot name="actions" />
    </div>
  </div>
</template>
