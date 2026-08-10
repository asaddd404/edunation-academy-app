<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";

import { downloadHomeworkFile, listPendingHomework, reviewHomework } from "@/api/homework";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
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
  <PageContainer>
    <PageHeader title="Домашние задания на проверку" />

    <div v-if="loading" class="space-y-4">
      <div v-for="i in 3" :key="i" class="h-40 animate-pulse rounded-xl bg-paper-2" />
    </div>

    <div v-else-if="!submissions.length" class="card py-12 text-center">
      <p class="text-3xl">✅</p>
      <p class="mt-3 text-ink-2">Нечего проверять — все домашние задания разобраны.</p>
    </div>

    <ul v-else class="space-y-4">
      <li v-for="submission in submissions" :key="submission.id" class="card marker-edge space-y-3 p-4">
        <div>
          <p class="font-medium text-ink">{{ submission.student_name }} — {{ submission.lesson_title }}</p>
          <p v-if="submission.text_answer" class="mt-2 whitespace-pre-line text-sm text-ink-2">{{ submission.text_answer }}</p>
          <button
            v-if="submission.file_original_name"
            class="mt-2 text-sm text-moss underline"
            @click="handleDownload(submission)"
          >
            Скачать файл: {{ submission.file_original_name }}
          </button>
        </div>
        <input
          v-model="feedback[submission.id]"
          placeholder="Комментарий (необязательно)"
          class="input"
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
  </PageContainer>
</template>
