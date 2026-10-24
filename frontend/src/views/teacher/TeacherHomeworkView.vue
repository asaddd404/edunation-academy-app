<script setup lang="ts">
import { BookOpen, CircleCheck, Clock, Phone, X } from "@lucide/vue";
import { computed, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { listHomework, reviewHomework } from "@/api/homework";
import HomeworkAttachment from "@/components/homework/HomeworkAttachment.vue";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { HomeworkListFilter, HomeworkStatus, HomeworkSubmission } from "@/types";
import { describeApiError } from "@/utils/apiError";

const route = useRoute();
const router = useRouter();

const TABS: { value: HomeworkListFilter; label: string }[] = [
  { value: "submitted", label: "На проверке" },
  { value: "reviewed", label: "Проверенные" },
  { value: "all", label: "Все" },
];

const STATUS: Record<HomeworkStatus, { label: string; classes: string }> = {
  submitted: {
    label: "Ожидает проверки",
    classes: "bg-amber-100 text-amber-900 ring-amber-300 dark:bg-amber-400/15 dark:text-amber-300 dark:ring-amber-400/30",
  },
  revision_requested: {
    label: "На доработке",
    classes: "bg-orange-100 text-orange-900 ring-orange-300 dark:bg-orange-400/15 dark:text-orange-300 dark:ring-orange-400/30",
  },
  accepted: {
    label: "Принято",
    classes: "bg-green-100 text-green-900 ring-green-300 dark:bg-green-400/15 dark:text-green-300 dark:ring-green-400/30",
  },
};

// The filter lives in the URL, so "all of this student's work" is a link
// the browser's back button returns from.
const tab = computed<HomeworkListFilter>(() => {
  const value = route.query.status;
  return TABS.some((t) => t.value === value) ? (value as HomeworkListFilter) : "submitted";
});
const studentId = computed(() => {
  const value = Number(route.query.student);
  return Number.isInteger(value) && value > 0 ? value : null;
});

const submissions = ref<HomeworkSubmission[]>([]);
const loading = ref(true);
const loadError = ref("");
const feedback = reactive<Record<number, string>>({});
// v-model on a type="number" input yields a number once typed, "" when cleared.
const grades = reactive<Record<number, number | string>>({});
const reviewingId = ref<number | null>(null);
const reviewError = reactive<Record<number, string>>({});

const studentName = computed(() =>
  studentId.value ? submissions.value.find((s) => s.student_id === studentId.value)?.student_name ?? "ученик" : null,
);

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    submissions.value = await listHomework(tab.value, studentId.value);
  } catch (e) {
    loadError.value = describeApiError(e, "Не удалось загрузить домашние задания.");
  } finally {
    loading.value = false;
  }
}

watch([tab, studentId], load, { immediate: true });

function setTab(value: HomeworkListFilter) {
  router.replace({ query: { ...route.query, status: value } });
}

function showStudent(submission: HomeworkSubmission) {
  router.push({ query: { status: "all", student: String(submission.student_id) } });
}

function clearStudent() {
  const query = { ...route.query };
  delete query.student;
  router.push({ query });
}

function parseGrade(id: number): number | null | undefined {
  const raw = String(grades[id] ?? "").trim();
  if (!raw) return null;
  const value = Number(raw);
  return Number.isInteger(value) && value >= 0 && value <= 100 ? value : undefined;
}

async function handleReview(submission: HomeworkSubmission, status: "accepted" | "revision_requested") {
  const grade = parseGrade(submission.id);
  if (grade === undefined) {
    reviewError[submission.id] = "Оценка — целое число от 0 до 100.";
    return;
  }
  reviewError[submission.id] = "";
  reviewingId.value = submission.id;
  try {
    const updated = await reviewHomework(submission.id, status, feedback[submission.id] || undefined, grade);
    if (tab.value === "submitted") {
      submissions.value = submissions.value.filter((s) => s.id !== submission.id);
    } else {
      Object.assign(submission, updated);
    }
  } catch (e) {
    reviewError[submission.id] = describeApiError(e, "Не удалось сохранить проверку.");
  } finally {
    reviewingId.value = null;
  }
}

const DATE_TIME = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "long",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function formatDateTime(iso: string): string {
  return DATE_TIME.format(new Date(iso));
}

function ago(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 60) return minutes <= 1 ? "только что" : `${minutes} мин назад`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  const days = Math.round(hours / 24);
  return `${days} дн назад`;
}

function gradeTone(grade: number): string {
  if (grade >= 85) return "text-moss";
  if (grade >= 60) return "text-ink";
  return "text-clay";
}
</script>

<template>
  <PageContainer>
    <PageHeader title="Домашние задания">
      <template #subtitle>
        Работы учеников по вашим курсам: фото и файлы открываются прямо здесь.
      </template>
    </PageHeader>

    <div class="mb-5 flex flex-wrap items-center gap-3">
      <div class="inline-flex rounded-xl border border-line bg-paper p-1" role="tablist" aria-label="Статус работ">
        <button
          v-for="t in TABS"
          :key="t.value"
          role="tab"
          :aria-selected="tab === t.value"
          class="rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors"
          :class="tab === t.value ? 'bg-moss text-moss-fg shadow-sm' : 'text-ink-2 hover:bg-paper-2'"
          @click="setTab(t.value)"
        >
          {{ t.label }}
          <span v-if="t.value === tab && !loading" class="ml-1 opacity-80">{{ submissions.length }}</span>
        </button>
      </div>
      <span
        v-if="studentId"
        class="inline-flex items-center gap-2 rounded-full border border-line bg-paper px-3 py-1.5 text-sm text-ink"
      >
        Работы ученика: <strong class="font-semibold">{{ studentName }}</strong>
        <button class="rounded-full p-0.5 text-ink-3 hover:bg-paper-2 hover:text-ink" aria-label="Показать всех учеников" @click="clearStudent">
          <X :size="14" />
        </button>
      </span>
    </div>

    <div v-if="loading" class="space-y-4">
      <div v-for="i in 3" :key="i" class="h-48 animate-pulse rounded-xl bg-paper-2" />
    </div>

    <div v-else-if="loadError" class="card py-10 text-center">
      <p class="text-ink-2">{{ loadError }}</p>
      <BaseButton variant="secondary" class="mt-4" @click="load">Повторить</BaseButton>
    </div>

    <div v-else-if="!submissions.length" class="card py-12 text-center">
      <CircleCheck :size="30" :stroke-width="1.6" class="mx-auto text-green-700 dark:text-green-500" />
      <p class="mt-3 text-ink-2">
        {{ tab === "submitted" ? "Нечего проверять — все домашние задания разобраны." : "Здесь пока нет работ." }}
      </p>
    </div>

    <ul v-else class="space-y-4">
      <li v-for="submission in submissions" :key="submission.id" class="card space-y-4 p-4 sm:p-5">
        <!-- Who, what, when -->
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <button
              class="text-left font-display text-lg font-semibold text-ink underline-offset-4 hover:text-moss hover:underline"
              :title="`Все работы ученика ${submission.student_name}`"
              @click="showStudent(submission)"
            >
              {{ submission.student_name }}
            </button>
            <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-ink-2">
              <router-link
                v-if="submission.category_id"
                :to="`/teacher/categories/${submission.category_id}`"
                class="inline-flex items-center gap-1 hover:text-moss hover:underline"
              >
                <BookOpen :size="14" /> {{ submission.category_name }}
              </router-link>
              <span class="text-ink">· {{ submission.lesson_title }}</span>
              <a
                v-if="submission.student_phone"
                :href="`tel:${submission.student_phone}`"
                class="inline-flex items-center gap-1 text-ink-3 hover:text-moss"
              >
                <Phone :size="13" /> {{ submission.student_phone }}
              </a>
            </div>
          </div>
          <span class="badge shrink-0 ring-1" :class="STATUS[submission.status].classes">
            {{ STATUS[submission.status].label }}
          </span>
        </div>

        <p class="flex items-center gap-1.5 text-xs text-ink-3">
          <Clock :size="13" />
          Отправлено {{ formatDateTime(submission.submitted_at) }}
          <span class="text-ink-3/80">({{ ago(submission.submitted_at) }})</span>
        </p>

        <p v-if="submission.text_answer" class="whitespace-pre-line rounded-xl bg-paper-2/60 px-3.5 py-3 text-sm text-ink">
          {{ submission.text_answer }}
        </p>

        <HomeworkAttachment v-if="submission.file_original_name" :submission="submission" />

        <!-- Review -->
        <div v-if="submission.status === 'submitted'" class="space-y-3 border-t border-line pt-4">
          <textarea
            v-model="feedback[submission.id]"
            rows="2"
            placeholder="Комментарий ученику (необязательно)"
            class="input min-h-[2.75rem] resize-y"
          />
          <div class="flex flex-wrap items-end gap-3">
            <label class="flex flex-col gap-1 text-xs font-medium text-ink-2">
              Оценка
              <span class="flex items-center gap-1.5">
                <input
                  v-model="grades[submission.id]"
                  type="number"
                  inputmode="numeric"
                  min="0"
                  max="100"
                  placeholder="—"
                  class="input w-24 text-center"
                  :aria-label="`Оценка для ${submission.student_name}, от 0 до 100`"
                />
                <span class="text-sm text-ink-3">/ 100</span>
              </span>
            </label>
            <div class="flex flex-1 flex-wrap justify-end gap-2">
              <BaseButton
                variant="secondary"
                :disabled="reviewingId === submission.id"
                @click="handleReview(submission, 'revision_requested')"
              >
                На доработку
              </BaseButton>
              <BaseButton :disabled="reviewingId === submission.id" @click="handleReview(submission, 'accepted')">
                Принять
              </BaseButton>
            </div>
          </div>
          <p v-if="reviewError[submission.id]" class="text-sm text-clay">{{ reviewError[submission.id] }}</p>
        </div>

        <div v-else class="flex flex-wrap items-start gap-4 border-t border-line pt-4 text-sm">
          <div v-if="submission.grade !== null" class="shrink-0">
            <p class="text-xs text-ink-3">Оценка</p>
            <p class="font-display text-2xl font-semibold" :class="gradeTone(submission.grade)">
              {{ submission.grade }}<span class="text-sm font-normal text-ink-3"> / 100</span>
            </p>
          </div>
          <div class="min-w-0 flex-1">
            <p class="text-xs text-ink-3">
              Проверено{{ submission.reviewed_at ? ` ${formatDateTime(submission.reviewed_at)}` : "" }}
            </p>
            <p v-if="submission.teacher_feedback" class="mt-1 text-ink">{{ submission.teacher_feedback }}</p>
          </div>
        </div>
      </li>
    </ul>
  </PageContainer>
</template>
