<script setup lang="ts">
import { Maximize2, Minimize2, Presentation, RotateCw } from "@lucide/vue";
import { onBeforeUnmount, onMounted, ref } from "vue";

import type { PresentationLink } from "@/api/presentation";
import { formatFileSize } from "@/api/presentation";

/**
 * A lesson's PowerPoint file, rendered by Microsoft's Office viewer in an
 * iframe -- the slides keep their own layout, fonts and animations.
 *
 * The viewer link is asked for only when this component mounts (the lesson
 * page mounts it when the presentation is actually shown), because each link
 * makes Microsoft download the file.
 */
const props = defineProps<{
  name: string;
  size?: number | null;
  loadLink: () => Promise<PresentationLink>;
}>();

const embedUrl = ref<string | null>(null);
const linkError = ref(false);
const frameLoaded = ref(false);
const isFullscreen = ref(false);
const shell = ref<HTMLElement | null>(null);

async function fetchLink() {
  linkError.value = false;
  frameLoaded.value = false;
  embedUrl.value = null;
  try {
    embedUrl.value = (await props.loadLink()).embed_url;
  } catch {
    linkError.value = true;
  }
}

function syncFullscreen() {
  isFullscreen.value = document.fullscreenElement === shell.value;
}

async function toggleFullscreen() {
  if (document.fullscreenElement) await document.exitFullscreen();
  else await shell.value?.requestFullscreen?.();
}

onMounted(() => {
  fetchLink();
  document.addEventListener("fullscreenchange", syncFullscreen);
});
onBeforeUnmount(() => document.removeEventListener("fullscreenchange", syncFullscreen));
</script>

<template>
  <div
    ref="shell"
    class="overflow-hidden rounded-2xl border border-line bg-paper shadow-sm"
    :class="isFullscreen ? 'flex h-screen flex-col rounded-none border-0' : ''"
  >
    <div class="flex items-center gap-3 border-b border-line px-3 py-2.5 sm:px-4">
      <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-clay/10 text-clay">
        <Presentation :size="18" :stroke-width="1.8" />
      </span>
      <div class="min-w-0 flex-1">
        <p class="truncate text-sm font-medium text-ink" :title="name">{{ name }}</p>
        <p class="text-xs text-ink-3">
          Презентация<template v-if="size"> · {{ formatFileSize(size) }}</template>
        </p>
      </div>
      <button
        type="button"
        class="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-line bg-paper px-2.5 text-sm font-medium text-ink-2 transition-colors hover:border-moss/50 hover:text-ink disabled:opacity-50 sm:px-3"
        :disabled="!embedUrl"
        :aria-label="isFullscreen ? 'Выйти из полноэкранного режима' : 'Открыть на весь экран'"
        @click="toggleFullscreen"
      >
        <component :is="isFullscreen ? Minimize2 : Maximize2" :size="15" :stroke-width="1.8" />
        <span class="hidden sm:inline">{{ isFullscreen ? "Свернуть" : "На весь экран" }}</span>
      </button>
    </div>

    <!-- 16:9 for the slide plus room for the viewer's own toolbar beneath it,
         so the slide is not letterboxed inside the frame. -->
    <div
      class="relative w-full bg-paper-2"
      :class="isFullscreen ? 'flex-1' : ''"
      :style="isFullscreen ? undefined : { paddingBottom: 'calc(56.25% + 2.25rem)' }"
    >
      <iframe
        v-if="embedUrl"
        :src="embedUrl"
        :title="`Презентация: ${name}`"
        class="absolute inset-0 h-full w-full border-0"
        referrerpolicy="no-referrer"
        allowfullscreen
        @load="frameLoaded = true"
      />
      <div
        v-if="!frameLoaded"
        class="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center"
      >
        <template v-if="linkError">
          <p class="text-sm text-clay">Не удалось открыть презентацию.</p>
          <button
            type="button"
            class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line bg-paper px-3 text-sm font-medium text-ink-2 hover:text-ink"
            @click="fetchLink"
          >
            <RotateCw :size="14" :stroke-width="1.8" />
            Повторить
          </button>
        </template>
        <template v-else>
          <span class="h-8 w-8 animate-spin rounded-full border-2 border-line border-t-moss" aria-hidden="true" />
          <p class="text-sm text-ink-2">Загружаем презентацию…</p>
        </template>
      </div>
    </div>

    <p v-if="!isFullscreen" class="border-t border-line px-3 py-2 text-xs text-ink-3 sm:px-4">
      Листайте кликом по слайду или стрелками ← →. Презентация открывается через просмотрщик Microsoft Office.
    </p>
  </div>
</template>
