<script setup lang="ts">
import { MonitorPlay, Presentation } from "@lucide/vue";
import { isAxiosError } from "axios";
import { computed, defineAsyncComponent, onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import { submitHomework } from "@/api/homework";
import { getLesson, startLessonTest } from "@/api/lessons";
import { listSections } from "@/api/sections";
import { getStudentPresentationLink } from "@/api/presentation";
import { getStudentVideoTicket } from "@/api/video";
import PresentationViewer from "@/components/media/PresentationViewer.vue";
import YouTubeEmbed from "@/components/media/YouTubeEmbed.vue";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import RichContent from "@/components/richtext/RichContent.vue";
import HwStudent from "@/components/autohw/HwStudent.vue";
import CourseTestPanel from "@/components/test/CourseTestPanel.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BackLink from "@/components/ui/BackLink.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import FilePicker from "@/components/ui/FilePicker.vue";
import type { LessonDetail, Section } from "@/types";
import { isRichDocEmpty, parseRichContent } from "@/utils/richContent";
import { describeApiError } from "@/utils/apiError";

// hls.js is ~500 kB -- most of this page's weight -- and only lessons with an
// uploaded video need it; YouTube lessons and text-only ones never load it.
const HlsPlayer = defineAsyncComponent(() => import("@/components/media/HlsPlayer.vue"));

const route = useRoute();
const lessonId = Number(route.params.id);

const lesson = ref<LessonDetail | null>(null);
const loading = ref(true);
const loadError = ref("");

const videoSrc = ref<string | null>(null);
const videoError = ref("");

// Video and presentation share one spot under the title. With both, a switch
// picks which is shown; the presentation viewer is mounted only once it is
// first opened, since every mount makes Microsoft download the file.
type MediaTab = "video" | "presentation";
const mediaTab = ref<MediaTab>("video");
const presentationOpened = ref(false);
const mediaBox = ref<HTMLElement | null>(null);

const hasPresentation = computed(() => !!lesson.value?.presentation_name);
const hasVideoBlock = computed(() => {
  const l = lesson.value;
  if (!l) return false;
  return !!videoSrc.value || !!l.video_url || l.video_status !== "none" || !!videoError.value;
});

function showMedia(tab: MediaTab) {
  if (tab === "presentation") {
    presentationOpened.value = true;
    // A hidden <video> would keep talking over the slides.
    mediaBox.value?.querySelectorAll("video").forEach((video) => video.pause());
  }
  mediaTab.value = tab;
}

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

// ── Course navigation ───────────────────────────────────────────────────
// The page used to end at the homework card with no way on: a student had
// to go back to the catalog and find the next lesson by hand. The course's
// sections come from the same listing the catalog uses, so lock state
// matches what the catalog shows.
const courseSections = ref<Section[]>([]);

async function loadCourseSections() {
  const categoryId = lesson.value?.category_id;
  if (!categoryId) return;
  try {
    courseSections.value = await listSections(categoryId);
  } catch {
    courseSections.value = []; // navigation is a convenience; never block the lesson on it
  }
}

const backLink = computed(() => {
  const l = lesson.value;
  if (!l?.category_id) return "/catalog";
  return `/catalog?category=${l.category_id}&section=${l.section_id}`;
});

interface NextStep {
  to: string;
  kicker: string;
  title: string;
  locked: boolean;
}

const nextStep = computed<NextStep | null>(() => {
  const l = lesson.value;
  if (!l) return null;
  const ordered = [...courseSections.value].sort((a, b) => a.order_index - b.order_index || a.id - b.id);
  const sectionIndex = ordered.findIndex((s) => s.id === l.section_id);
  const section = ordered[sectionIndex];
  if (!section) return null;
  const lessons = [...section.lessons].sort((a, b) => a.order_index - b.order_index || a.id - b.id);
  const next = lessons[lessons.findIndex((x) => x.id === l.id) + 1];
  if (next) return { to: `/lessons/${next.id}`, kicker: "Следующий урок", title: next.title, locked: !next.is_unlocked };
  const sectionTest: NextStep | null = section.has_test
    ? { to: `/sections/${section.id}/test`, kicker: "Дальше", title: "Итоговый тест раздела", locked: !section.is_test_unlocked }
    : null;
  // An unpassed section test is the next thing to do; once it's passed the
  // way on is the next section, and the test is only offered again when the
  // course has nothing after it.
  if (sectionTest && !section.is_test_passed) return sectionTest;
  const nextSection = ordered[sectionIndex + 1];
  const first = nextSection && [...nextSection.lessons].sort((a, b) => a.order_index - b.order_index || a.id - b.id)[0];
  if (first)
    return { to: `/lessons/${first.id}`, kicker: `Следующий раздел · ${nextSection.title}`, title: first.title, locked: !first.is_unlocked };
  return sectionTest;
});

function handleLessonPassed() {
  if (lesson.value) lesson.value.is_passed = true;
  // Passing the mini-test is what unlocks the next step; refresh its state.
  loadCourseSections();
}

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    lesson.value = await getLesson(lessonId);
    homeworkText.value = lesson.value.my_homework?.text_answer ?? "";
    loadCourseSections();
    if (lesson.value.presentation_name && !hasVideoBlock.value) showMedia("presentation");
    if (lesson.value.video_status === "ready") {
      try {
        const ticket = await getStudentVideoTicket(lessonId);
        videoSrc.value = `${import.meta.env.VITE_API_BASE_URL}${ticket.playback_path}`;
      } catch {
        videoError.value = "Не удалось загрузить видео.";
      }
    }
  } catch (e) {
    // Only a 403 means "locked"; a 500 used to be explained the same way.
    const status = isAxiosError(e) ? e.response?.status : undefined;
    loadError.value =
      status === 403
        ? "Урок пока закрыт — сначала пройдите мини-тест предыдущего урока."
        : status === 404
          ? "Такого урока нет — возможно, его удалили."
          : describeApiError(e, "Не удалось загрузить урок.");
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
    // The server says what was wrong (file type, size, locked lesson).
    homeworkError.value = describeApiError(e, "Не удалось отправить домашнее задание.");
  } finally {
    homeworkSubmitting.value = false;
  }
}

</script>

<template>
  <PageContainer>
    <div v-if="loading" class="mx-auto max-w-3xl space-y-6">
      <div class="h-8 w-2/3 animate-pulse rounded-lg bg-paper-2"></div>
      <div class="h-64 w-full animate-pulse rounded-2xl bg-paper-2"></div>
      <div class="h-40 w-full animate-pulse rounded-2xl bg-paper-2"></div>
    </div>

    <div v-else-if="loadError" class="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-center">
      <p class="text-clay">{{ loadError }}</p>
      <BaseButton variant="secondary" @click="load">Повторить</BaseButton>
    </div>

    <div v-else-if="lesson" class="mx-auto max-w-3xl">
      <!-- One centred reading column: on a laptop the cards used to sit in a
           narrow strip on the left while the header's badge hung off the far
           right edge, half a screen away from anything it described. -->
      <BackLink :to="backLink" label="К курсу" class="mb-4" />
      <PageHeader :title="lesson.title">
        <template #actions>
          <BaseBadge :tone="lesson.is_passed ? 'success' : 'neutral'">
            {{ lesson.is_passed ? "Тест пройден" : "Тест не пройден" }}
          </BaseBadge>
        </template>
      </PageHeader>

      <div class="space-y-8">
        <section v-if="hasVideoBlock || hasPresentation" ref="mediaBox" class="space-y-3">
          <div
            v-if="hasVideoBlock && hasPresentation"
            role="tablist"
            aria-label="Материалы урока"
            class="inline-flex rounded-xl border border-line bg-paper-2 p-1"
          >
            <button
              v-for="tab in ([
                { key: 'video', label: 'Видеоурок', icon: MonitorPlay },
                { key: 'presentation', label: 'Презентация', icon: Presentation },
              ] as const)"
              :key="tab.key"
              type="button"
              role="tab"
              :aria-selected="mediaTab === tab.key"
              class="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium transition-all duration-200"
              :class="mediaTab === tab.key ? 'bg-paper text-ink shadow-sm' : 'text-ink-2 hover:text-ink'"
              @click="showMedia(tab.key)"
            >
              <component :is="tab.icon" :size="15" :stroke-width="1.8" />
              {{ tab.label }}
            </button>
          </div>

          <div v-if="hasVideoBlock" v-show="mediaTab === 'video'">
            <HlsPlayer v-if="videoSrc" :src="videoSrc" />
            <YouTubeEmbed
              v-else-if="lesson.video_url && lesson.video_status !== 'processing' && mediaTab === 'video'"
              :url="lesson.video_url"
              :title="lesson.title"
            />
            <p v-else-if="lesson.video_status === 'processing'" class="rounded-xl border border-line p-4 text-sm text-ink-2">
              Видео обрабатывается, зайдите чуть позже.
            </p>
            <p v-else-if="lesson.video_status === 'failed'" class="rounded-xl border border-line p-4 text-sm text-clay">
              Не удалось обработать видео. Сообщите учителю.
            </p>
            <p v-else-if="videoError" class="rounded-xl border border-line p-4 text-sm text-clay">{{ videoError }}</p>
          </div>

          <PresentationViewer
            v-if="hasPresentation && presentationOpened"
            v-show="mediaTab === 'presentation'"
            :name="lesson.presentation_name ?? 'Презентация'"
            :size="lesson.presentation_size"
            :load-link="() => getStudentPresentationLink(lessonId)"
          />
        </section>

        <RichContent :content="lesson.description" />

        <div class="space-y-8">
          <CourseTestPanel
            v-if="lesson.question_count"
            title="Мини-тест"
            :question-count="lesson.question_count"
            :is-passed="lesson.is_passed"
            :start="() => startLessonTest(lessonId)"
            :leaderboard-to="{ path: '/leaderboard', query: { lesson: lessonId } }"
            @passed="handleLessonPassed"
          />

          <HwStudent :lesson-id="lessonId" :title="hasHomework ? 'Домашнее задание с автопроверкой' : undefined" />

          <section v-if="hasHomework" class="card space-y-3 p-4 sm:p-5">
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
              <p v-if="lesson.my_homework.grade !== null && lesson.my_homework.grade !== undefined" class="mt-2">
                Оценка: <strong class="font-semibold">{{ lesson.my_homework.grade }} / 100</strong>
              </p>
              <p v-if="lesson.my_homework.teacher_feedback" class="mt-2">
                Комментарий учителя: {{ lesson.my_homework.teacher_feedback }}
              </p>
            </div>

            <!-- Accepted work is final: the server refuses a resubmission, which
                 would otherwise wipe the teacher's grade and comment. -->
            <p v-if="lesson.my_homework?.status === 'accepted'" class="text-sm text-ink-2">
              Работа принята учителем — повторно отправлять её не нужно.
            </p>
            <template v-else>
            <textarea v-model="homeworkText" rows="4" maxlength="20000" placeholder="Текст ответа…" class="input" />
            <div class="space-y-1.5">
              <FilePicker
                :file="homeworkFile"
                accept=".jpg,.jpeg,.png,.pdf,.txt,.doc,.docx"
                label="Прикрепить решение"
                @pick="homeworkFile = $event"
                @clear="homeworkFile = null"
              />
              <p class="text-xs text-ink-3">
                <template v-if="lesson.my_homework?.file_original_name && !homeworkFile">
                  {{ lesson.my_homework.file_deleted ? "Был прикреплён (удалён по истечении срока хранения)" : "Уже прикреплён" }}:
                  {{ lesson.my_homework.file_original_name }} ·
                </template>
                jpg, png, pdf, txt, doc
              </p>
            </div>
            <p v-if="homeworkError" class="text-sm text-clay">{{ homeworkError }}</p>
            <BaseButton variant="cta" :disabled="homeworkSubmitting" @click="handleSubmitHomework">
              Отправить домашку
            </BaseButton>
            </template>
          </section>
        </div>
      </div>

      <component
        :is="nextStep.locked ? 'div' : 'router-link'"
        v-if="nextStep"
        :to="nextStep.locked ? undefined : nextStep.to"
        class="group mt-6 flex items-center justify-between gap-4 rounded-2xl border p-4 transition-all duration-200 sm:p-5"
        :class="
          nextStep.locked
            ? 'border-dashed border-line-strong text-ink-3'
            : 'border-line bg-paper hover:border-moss/50 hover:shadow-sm'
        "
        :aria-disabled="nextStep.locked ? 'true' : undefined"
      >
        <span class="min-w-0">
          <span class="block text-xs font-medium uppercase tracking-wide text-ink-3">{{ nextStep.kicker }}</span>
          <span class="mt-0.5 block font-semibold leading-snug" :class="nextStep.locked ? 'text-ink-3' : 'text-ink'">
            {{ nextStep.title }}
          </span>
          <span v-if="nextStep.locked" class="mt-1 block text-xs">Откроется после мини-теста этого урока</span>
        </span>
        <span
          v-if="!nextStep.locked"
          class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-moss text-moss-fg transition-transform duration-200 group-hover:translate-x-0.5"
          aria-hidden="true"
        >
          <svg class="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M6 3 l5 5 -5 5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </span>
      </component>
    </div>
  </PageContainer>
</template>
