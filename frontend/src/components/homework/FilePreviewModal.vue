<script setup lang="ts">
import { Download, X } from "@lucide/vue";
import { ref } from "vue";

import { useModalFocusTrap } from "@/composables/useModalFocusTrap";

/**
 * Full-screen preview of a homework image or PDF, so the teacher reads the
 * work in place instead of downloading every file. `url` is a blob: URL the
 * caller owns (and revokes).
 */
defineProps<{ url: string; kind: "image" | "pdf"; name: string }>();
const emit = defineEmits<{ close: []; download: [] }>();

const root = ref<HTMLElement | null>(null);
useModalFocusTrap(root, () => emit("close"));
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-[70] flex flex-col bg-black/85 backdrop-blur-sm" @click.self="emit('close')">
      <div ref="root" role="dialog" aria-modal="true" :aria-label="`Просмотр: ${name}`" class="flex min-h-0 flex-1 flex-col">
        <div class="flex items-center justify-between gap-3 px-4 py-3 text-white">
          <p class="min-w-0 truncate text-sm font-medium">{{ name }}</p>
          <div class="flex shrink-0 items-center gap-2">
            <button
              class="flex h-10 items-center gap-2 rounded-lg bg-white/10 px-3 text-sm transition-colors hover:bg-white/20"
              @click="emit('download')"
            >
              <Download :size="16" /> Скачать
            </button>
            <button
              class="flex h-10 w-10 items-center justify-center rounded-lg bg-white/10 transition-colors hover:bg-white/20"
              aria-label="Закрыть просмотр"
              @click="emit('close')"
            >
              <X :size="18" />
            </button>
          </div>
        </div>
        <div class="flex min-h-0 flex-1 items-center justify-center px-4 pb-4" @click.self="emit('close')">
          <img v-if="kind === 'image'" :src="url" :alt="name" class="max-h-full max-w-full rounded-lg object-contain shadow-2xl" />
          <iframe v-else :src="url" :title="name" class="h-full w-full max-w-5xl rounded-lg bg-white" />
        </div>
      </div>
    </div>
  </Teleport>
</template>
