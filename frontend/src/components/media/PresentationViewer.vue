<script setup lang="ts">
import { ExternalLink, FileText, Maximize2, Minimize2, Presentation, RotateCw } from "@lucide/vue";
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import type { PresentationLink } from "@/api/presentation";
import { fetchPresentationPdf, formatFileSize, isPdfPresentation } from "@/api/presentation";

/**
 * A lesson's presentation.
 *
 * PowerPoint (.pptx/.ppsx) is rendered by Microsoft's Office viewer in an
 * iframe -- the slides keep their own layout, fonts and animations. A PDF is
 * fetched from our own short-lived link and shown by the browser's PDF
 * viewer from a blob: URL (the API refuses to be framed directly).
 *
 * The link is asked for only when this component mounts (the lesson page
 * mounts it when the presentation is actually shown), because for
 * PowerPoint each link makes Microsoft download the file.
 */
const props = defineProps<{
  name: string;
  size?: number | null;
  loadLink: () => Promise<PresentationLink>;
}>();

const frameSrc = ref<string | null>(null);
const pdfUrl = ref<string | null>(null);
const linkError = ref(false);
const frameLoaded = ref(false);
const isFullscreen = ref(false);
const shell = ref<HTMLElement | null>(null);

const isPdf = computed(() => isPdfPresentation(props.name));

function releasePdf() {
  if (pdfUrl.value) URL.revokeObjectURL(pdfUrl.value);
  pdfUrl.value = null;
}

async function fetchLink() {
  linkError.value = false;
  frameLoaded.value = false;
  frameSrc.value = null;
  releasePdf();
  try {
    const link = await props.loadLink();
    if (link.kind === "pdf" && link.file_path) {
      pdfUrl.value = URL.createObjectURL(await fetchPresentationPdf(link.file_path));
      frameSrc.value = pdfUrl.value;
    } else if (link.embed_url) {
      frameSrc.value = link.embed_url;
    } else {
      linkError.value = true;
    }
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
onBeforeUnmount(() => {
  document.removeEventListener("fullscreenchange", syncFullscreen);
  releasePdf();
});
</script>

<template>
  <div
    ref="shell"
    class="overflow-hidden rounded-2xl border border-line bg-paper shadow-sm"
    :class="isFullscreen ? 'flex h-screen flex-col rounded-none border-0' : ''"
  >
    <div class="flex items-center gap-3 border-b border-line px-3 py-2.5 sm:px-4">
      <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-clay/10 text-clay">
        <component :is="isPdf ? FileText : Presentation" :size="18" :stroke-width="1.8" />
      </span>
      <div class="min-w-0 flex-1">
        <p class="truncate text-sm font-medium text-ink" :title="name">{{ name }}</p>
        <p class="text-xs text-ink-3">
          {{ isPdf ? "PDF" : "Презентация" }}<template v-if="size"> · {{ formatFileSize(size) }}</template>
        </p>
      </div>
      <!-- Phones (Android Chrome above all) often refuse to render a PDF
           inside a page at all; a new tab always works. -->
      <a
        v-if="pdfUrl"
        :href="pdfUrl"
        target="_blank"
        rel="noopener"
        class="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-line bg-paper px-2.5 text-sm font-medium text-ink-2 transition-colors hover:border-moss/50 hover:text-ink sm:px-3"
        aria-label="Открыть PDF в новой вкладке"
      >
        <ExternalLink :size="15" :stroke-width="1.8" />
        <span class="hidden sm:inline">Открыть</span>
      </a>
      <button
        type="button"
        class="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-line bg-paper px-2.5 text-sm font-medium text-ink-2 transition-colors hover:border-moss/50 hover:text-ink disabled:opacity-50 sm:px-3"
        :disabled="!frameSrc"
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
        v-if="frameSrc"
        :src="frameSrc"
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
      <template v-if="isPdf">
        Листайте прокруткой. Если PDF не отображается на телефоне, нажмите «Открыть».
      </template>
      <template v-else>
        Листайте кликом по слайду или стрелками ← →. Презентация открывается через просмотрщик Microsoft Office.
      </template>
    </p>
  </div>
</template>
