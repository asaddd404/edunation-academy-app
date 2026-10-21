<script setup lang="ts">
import { isAxiosError } from "axios";
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import { submitHomework } from "@/api/homework";
import { getLesson } from "@/api/lessons";
import { getStudentVideoTicket } from "@/api/video";
import HlsPlayer from "@/components/media/HlsPlayer.vue";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import RichContent from "@/components/richtext/RichContent.vue";
import TestRunner from "@/components/tests/TestRunner.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { LessonDetail } from "@/types";
import { isRichDocEmpty, parseRichContent } from "@/utils/richContent";

const route = useRoute();
const lessonId = Number(route.params.id);

const lesson = ref<LessonDetail | null>(null);
const loading = ref(true);
const loadError = ref("");

const videoSrc = ref<string | null>(null);
const videoError = ref("");

const homeworkText = ref("");
const homeworkFile = ref<File | null>(null);
const homeworkSubmitting = ref(false);
const homeworkError = ref("");

// A cleared rich-text field still stores a non-empty JSON string (an empty
// paragraph), so a plain truthiness check would render a blank homework card.
const hasHomework = computed(() => {
  const raw = lesson.value?.homework_assignment;
  const parsed = parseRichContent(raw);
  if (parsed.kind === "empty") return false;
  return parsed.kind === "plain" || !isRichDocEmpty(parsed.doc);
});

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    lesson.value = await getLesson(lessonId);
    homeworkText.value = lesson.value.my_homework?.text_answer ?? "";
    if (lesson.value.video_status === "ready") {
      try {
        const ticket = await getStudentVideoTicket(lessonId);
        videoSrc.value = `${import.meta.env.VITE_API_BASE_URL}${ticket.playback_path}`;
      } catch {
        videoError.value = "Не удалось загрузить видео.";
      }
    }
  } catch {
    loadError.value = "Урок недоступен — возможно, он ещё заблокирован.";
  } finally {
    loading.value = false;
  }
}

onMounted(load);

async function handleSubmitHomework() {
  homeworkSubmitting.value = true;
  homeworkError.value = "";
  try {
    const submission = await submitHomework(lessonId, homeworkText.value, homeworkFile.value);
    if (lesson.value) lesson.value.my_homework = submission;
    homeworkFile.value = null;
  } catch (e) {
    const detail = isAxiosError(e) ? e.response?.data?.detail : null;
    homeworkError.value = typeof detail === "string" ? detail : "Не удалось отправить домашнее задание.";
  } finally {
    homeworkSubmitting.value = false;
  }
}

function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  homeworkFile.value = input.files?.[0] ?? null;
}
</script>

<template>
  <PageContainer>
    <div v-if="loading" class="space-y-6">
      <div class="h-8 w-2/3 animate-pulse rounded-lg bg-paper-2"></div>
      <div class="h-64 w-full animate-pulse rounded-2xl bg-paper-2"></div>
      <div class="h-40 w-full max-w-[42rem] animate-pulse rounded-2xl bg-paper-2"></div>
    </div>

    <div v-else-if="loadError" class="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-center">
      <p class="text-clay">{{ loadError }}</p>
      <BaseButton variant="secondary" @click="load">Повторить</BaseButton>
    </div>

    <template v-else-if="lesson">
      <PageHeader :title="lesson.title">
        <template #actions>
          <BaseBadge :tone="lesson.is_passed ? 'success' : 'neutral'">
            {{ lesson.is_passed ? "Тест пройден" : "Тест не пройден" }}
          </BaseBadge>
        </template>
      </PageHeader>

      <div class="space-y-8">
        <HlsPlayer v-if="videoSrc" :src="videoSrc" />
        <p v-else-if="lesson.video_status === 'processing'" class="rounded-xl border border-line p-4 text-sm text-ink-2">
          Видео обрабатывается, зайдите чуть позже.
        </p>
        <p v-else-if="lesson.video_status === 'failed'" class="rounded-xl border border-line p-4 text-sm text-clay">
          Не удалось обработать видео. Сообщите учителю.
        </p>
        <p v-else-if="videoError" class="rounded-xl border border-line p-4 text-sm text-clay">{{ videoError }}</p>

        <RichContent :content="lesson.description" class="max-w-[70ch]" />

        <div class="max-w-[42rem] space-y-8">
          <TestRunner v-if="lesson.has_test" kind="lesson" :id="lesson.id" @passed="lesson.is_passed = true" />

          <section v-if="hasHomework" class="card space-y-3 p-4">
            <h2 class="text-lg font-medium text-ink">Домашнее задание</h2>
            <RichContent :content="lesson.homework_assignment" />

            <div v-if="lesson.my_homework" class="rounded-lg bg-paper-2 p-3 text-sm text-ink">
              <p>
                Статус:
                <BaseBadge
                  :tone="
                    lesson.my_homework.status === 'accepted'
                      ? 'success'
                      : lesson.my_homework.status === 'revision_requested'
                        ? 'danger'
                        : 'warning'
                  "
                >
                  {{
                    lesson.my_homework.status === "accepted"
                      ? "Принято"
                      : lesson.my_homework.status === "revision_requested"
                        ? "На доработку"
                        : "На проверке"
                  }}
                </BaseBadge>
              </p>
              <p v-if="lesson.my_homework.teacher_feedback" class="mt-2">
                Комментарий учителя: {{ lesson.my_homework.teacher_feedback }}
              </p>
            </div>

            <!-- Accepted work is final: the server refuses a resubmission
                 that would discard the teacher's review. -->
            <template v-if="lesson.my_homework?.status !== 'accepted'">
              <textarea v-model="homeworkText" rows="4" maxlength="20000" placeholder="Текст ответа…" class="input" />
              <input type="file" accept=".jpg,.jpeg,.png,.pdf,.txt,.doc,.docx" class="text-sm text-ink-2" @change="handleFileChange" />
              <p v-if="homeworkError" class="text-sm text-clay">{{ homeworkError }}</p>
              <BaseButton variant="cta" :disabled="homeworkSubmitting" @click="handleSubmitHomework">
                Отправить домашку
              </BaseButton>
            </template>
          </section>
        </div>
      </div>
    </template>
  </PageContainer>
</template>
