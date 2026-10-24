<script setup lang="ts">
import { Download, Eye, FileText, ImageOff } from "@lucide/vue";
import { onBeforeUnmount, onMounted, ref } from "vue";

import { downloadHomeworkFile, fetchHomeworkFileUrl } from "@/api/homework";
import FilePreviewModal from "@/components/homework/FilePreviewModal.vue";
import type { HomeworkSubmission } from "@/types";

/**
 * A student's attached file on a review card: a thumbnail for photos, a
 * tile for PDFs and documents, with "Просмотреть" (images and PDFs, in a
 * full-screen preview) and "Скачать".
 */
const props = defineProps<{ submission: HomeworkSubmission }>();

const previewUrl = ref<string | null>(null);
const previewOpen = ref(false);
const loadFailed = ref(false);
const loading = ref(false);

const kind = props.submission.file_kind;
const name = props.submission.file_original_name ?? "файл";
const canPreview = kind === "image" || kind === "pdf";

async function ensureUrl(): Promise<string | null> {
  if (previewUrl.value) return previewUrl.value;
  loading.value = true;
  try {
    previewUrl.value = await fetchHomeworkFileUrl(props.submission.id, true);
    return previewUrl.value;
  } catch {
    loadFailed.value = true;
    return null;
  } finally {
    loading.value = false;
  }
}

async function openPreview() {
  if (await ensureUrl()) previewOpen.value = true;
}

function download() {
  void downloadHomeworkFile(props.submission.id, name);
}

// Photos get a thumbnail straight away -- the teacher sees the work without
// a click. PDFs load only when opened.
onMounted(() => {
  if (kind === "image") void ensureUrl();
});
onBeforeUnmount(() => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value);
});
</script>

<template>
  <div class="flex flex-col gap-3 rounded-xl border border-line bg-paper-2/50 p-3 sm:flex-row sm:items-center">
    <button
      v-if="kind === 'image'"
      class="group relative h-28 w-full shrink-0 overflow-hidden rounded-lg border border-line bg-paper sm:w-36"
      :aria-label="`Открыть фото: ${name}`"
      @click="openPreview"
    >
      <img v-if="previewUrl" :src="previewUrl" alt="" class="h-full w-full object-cover transition-transform duration-200 group-hover:scale-105" />
      <span v-else-if="loadFailed" class="flex h-full items-center justify-center text-ink-3"><ImageOff :size="22" /></span>
      <span v-else class="block h-full w-full animate-pulse bg-paper-2" />
    </button>
    <span
      v-else
      class="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg font-semibold"
      :class="kind === 'pdf' ? 'bg-clay/15 text-clay' : 'bg-paper text-ink-2'"
    >
      <FileText :size="24" />
    </span>

    <div class="min-w-0 flex-1">
      <p class="truncate text-sm font-medium text-ink">{{ name }}</p>
      <p class="text-xs text-ink-3">
        {{ kind === "image" ? "Фото" : kind === "pdf" ? "PDF-документ" : "Документ — откроется после скачивания" }}
      </p>
      <p v-if="loadFailed" class="mt-1 text-xs text-clay">Не удалось загрузить файл.</p>
    </div>

    <div class="flex shrink-0 gap-2">
      <button
        v-if="canPreview"
        class="btn-primary flex items-center gap-1.5 px-3 py-2 text-sm"
        :disabled="loading"
        @click="openPreview"
      >
        <Eye :size="16" /> {{ loading ? "Загрузка…" : "Просмотреть" }}
      </button>
      <button class="btn-ghost flex items-center gap-1.5 px-3 py-2 text-sm" @click="download">
        <Download :size="16" /> Скачать
      </button>
    </div>

    <FilePreviewModal
      v-if="previewOpen && previewUrl && canPreview"
      :url="previewUrl"
      :kind="kind as 'image' | 'pdf'"
      :name="name"
      @close="previewOpen = false"
      @download="download"
    />
  </div>
</template>
