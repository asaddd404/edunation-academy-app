<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";

import { downloadHomeworkFile, listPendingHomework, reviewHomework } from "@/api/homework";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { HomeworkSubmission } from "@/types";

const submissions = ref<HomeworkSubmission[]>([]);
const loading = ref(true);
const feedback = reactive<Record<number, string>>({});
const reviewingId = ref<number | null>(null);

async function load() {
  loading.value = true;
  submissions.value = await listPendingHomework();
  loading.value = false;
}

onMounted(load);

async function handleReview(id: number, status: "accepted" | "revision_requested") {
  reviewingId.value = id;
  try {
    await reviewHomework(id, status, feedback[id] || undefined);
    submissions.value = submissions.value.filter((s) => s.id !== id);
  } finally {
    reviewingId.value = null;
  }
}

function handleDownload(submission: HomeworkSubmission) {
  if (submission.file_original_name) {
    downloadHomeworkFile(submission.id, submission.file_original_name);
  }
}
</script>

<template>
  <div>
    <h1 class="mb-6 text-2xl font-semibold">Домашние задания на проверку</h1>
    <p v-if="loading" class="text-fg/60">Загрузка…</p>
    <p v-else-if="!submissions.length" class="text-fg/60">Нечего проверять.</p>
    <ul class="space-y-4">
      <li v-for="submission in submissions" :key="submission.id" class="space-y-3 rounded-xl border border-fg/10 p-4">
        <div>
          <p class="font-medium">{{ submission.student_name }} — {{ submission.lesson_title }}</p>
          <p v-if="submission.text_answer" class="mt-2 whitespace-pre-line text-sm text-fg/80">{{ submission.text_answer }}</p>
          <button
            v-if="submission.file_original_name"
            class="mt-2 text-sm text-accent underline"
            @click="handleDownload(submission)"
          >
            Скачать файл: {{ submission.file_original_name }}
          </button>
        </div>
        <input
          v-model="feedback[submission.id]"
          placeholder="Комментарий (необязательно)"
          class="w-full rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm"
        />
        <div class="flex gap-2">
          <BaseButton variant="secondary" :disabled="reviewingId === submission.id" @click="handleReview(submission.id, 'revision_requested')">
            На доработку
          </BaseButton>
          <BaseButton :disabled="reviewingId === submission.id" @click="handleReview(submission.id, 'accepted')">
            Принять
          </BaseButton>
        </div>
      </li>
    </ul>
  </div>
</template>
