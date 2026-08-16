<script setup lang="ts">
/**
 * Standard "go back" control: a circular arrow that slides left on hover,
 * with the label sitting beside it. Used instead of a bare "← текст" link so
 * the target is a real 40px tap area on a phone rather than a line of text.
 */
withDefaults(defineProps<{ to: string; label?: string }>(), { label: "Назад" });
</script>

<template>
  <router-link
    :to="to"
    class="group inline-flex items-center gap-2 rounded-full border border-line bg-paper py-1.5 pl-1.5 pr-4 text-sm font-medium text-ink-2 transition-all duration-200 ease-out hover:border-moss/50 hover:text-ink hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-moss focus-visible:ring-offset-2 focus-visible:ring-offset-sand"
  >
    <span
      class="flex h-7 w-7 items-center justify-center rounded-full bg-paper-2 text-ink-2 transition-colors duration-200 group-hover:bg-moss group-hover:text-moss-fg"
    >
      <svg class="h-3.5 w-3.5 transition-transform duration-200 group-hover:-translate-x-0.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M10 3 L5 8 l5 5" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </span>
    {{ label }}
  </router-link>
</template>
