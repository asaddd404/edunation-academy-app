<script setup lang="ts">
import { CheckCircle2, Info, TriangleAlert, X } from "@lucide/vue";

import { useToastStore } from "@/stores/toast";

const toasts = useToastStore();

const ICON = { error: TriangleAlert, success: CheckCircle2, info: Info } as const;
const TONE = {
  error: "border-red-500/30 bg-red-50 text-red-800 dark:bg-red-950/90 dark:text-red-200",
  success: "border-green-600/30 bg-green-50 text-green-800 dark:bg-green-950/90 dark:text-green-200",
  info: "border-line bg-paper text-ink",
} as const;
</script>

<template>
  <!-- Bottom-centre on a phone, bottom-right on wider screens, above the
       home indicator; announced to screen readers as it appears. -->
  <div
    class="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex flex-col items-center gap-2 px-4 sm:items-end"
    :style="{ paddingBottom: 'calc(1rem + env(safe-area-inset-bottom, 0px))' }"
    aria-live="polite"
    role="status"
  >
    <TransitionGroup
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="translate-y-2 opacity-0"
      leave-active-class="transition duration-150 ease-in"
      leave-to-class="opacity-0"
    >
      <div
        v-for="toast in toasts.items"
        :key="toast.id"
        class="pointer-events-auto flex w-full max-w-sm items-start gap-2.5 rounded-xl border p-3 text-sm shadow-lg backdrop-blur"
        :class="TONE[toast.tone]"
      >
        <component :is="ICON[toast.tone]" :size="18" :stroke-width="2" class="mt-px shrink-0" />
        <p class="min-w-0 flex-1">{{ toast.message }}</p>
        <button
          type="button"
          class="shrink-0 rounded-md p-0.5 opacity-70 hover:opacity-100"
          aria-label="Закрыть уведомление"
          @click="toasts.dismiss(toast.id)"
        >
          <X :size="16" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>
