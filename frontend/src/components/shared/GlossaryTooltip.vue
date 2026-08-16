<script setup lang="ts">
import { ref } from "vue";

/**
 * One dotted-underlined glossary term plus its explanation. Shared by both
 * renderers so the two never drift apart: `SmartText` (legacy plain text
 * carrying `[Термин|Объяснение]`) and `RichContent` (the glossaryTerm mark in
 * a TipTap document).
 *
 * Desktop gets a hover popover; coarse-pointer screens get a tap-to-open
 * bottom sheet, since there is no hover to reveal it with.
 */
defineProps<{ term: string; explanation: string }>();

const sheetOpen = ref(false);
</script>

<template>
  <span class="group/term relative inline-block">
    <button
      type="button"
      class="border-b border-dashed border-moss font-medium text-moss transition-colors hover:text-moss/80"
      @click="sheetOpen = !sheetOpen"
    >
      {{ term }}
    </button>
    <span
      class="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 hidden w-56 -translate-x-1/2 rounded-lg border border-line bg-paper p-2.5 text-xs font-normal text-ink opacity-0 shadow-lg transition-opacity duration-150 group-hover/term:opacity-100 sm:block"
    >
      {{ explanation }}
    </span>
  </span>

  <Teleport to="body">
    <div v-if="sheetOpen" class="fixed inset-0 z-50 bg-black/40 sm:hidden" @click="sheetOpen = false" />
    <div
      v-if="sheetOpen"
      class="fixed inset-x-0 bottom-0 z-50 rounded-t-2xl border-t border-line bg-paper p-4 shadow-lg sm:hidden"
    >
      <p class="mb-1 font-semibold text-ink">{{ term }}</p>
      <p class="text-sm text-ink-2">{{ explanation }}</p>
      <button class="btn-ghost mt-3 w-full" @click="sheetOpen = false">Закрыть</button>
    </div>
  </Teleport>
</template>
