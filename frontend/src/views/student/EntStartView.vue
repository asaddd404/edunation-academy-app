<script setup lang="ts">
import { Trophy } from "@lucide/vue";
import { isAxiosError } from "axios";
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { getEntLeaderboard, listEntSimulations, listEntSubjects, startEntSimulation } from "@/api/ent";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import LanguageChip from "@/components/ui/LanguageChip.vue";
import SubjectIcon from "@/components/ui/SubjectIcon.vue";
import type { EntLeaderboardEntry, EntSimulationSummary, EntSubject, ExamLanguage } from "@/types";
import { calcExamDurationMinutes, ENT_FULL_SUBJECT_COUNT, formatExamDuration } from "@/utils/examDuration";
import { EXAM_LANGUAGES, LANGUAGE_LABEL } from "@/utils/examLanguage";
import { scorePercent, scoreTone } from "@/utils/examOptions";
import { capitalize, pluralRu } from "@/utils/subjectTheme";

const router = useRouter();

const subjects = ref<EntSubject[]>([]);
const history = ref<EntSimulationSummary[]>([]);
const myRating = ref<EntLeaderboardEntry | null>(null);
const loading = ref(true);
const starting = ref(false);
const startError = ref("");
const accessDenied = ref(false);

const selectedSubjectIds = ref<number[]>([]);
const questionsPerSubject = ref(10);
// The language the exam is sat in: only questions in it are drawn. Russian
// by default, which is what every attempt before this option was.
const examLanguage = ref<ExamLanguage>("ru");
const isTimed = ref(true);

// Dynamic per real-ЕНТ rules: 48 minutes per selected subject, capped at the
// full exam's 240 (5 subjects x 48) -- no manual override.
const durationMinutes = computed(() => calcExamDurationMinutes(selectedSubjectIds.value.length));
const durationLabel = computed(() => formatExamDuration(durationMinutes.value));

const canStart = computed(() => selectedSubjectIds.value.length > 0 && questionsPerSubject.value >= 1);

const totalQuestions = computed(() => selectedSubjectIds.value.length * (questionsPerSubject.value || 0));

async function load() {
  loading.value = true;
  accessDenied.value = false;
  try {
    const [subjectsRes, historyRes, leaderboard] = await Promise.all([
      listEntSubjects(),
      listEntSimulations(),
      getEntLeaderboard(1),
    ]);
    subjects.value = subjectsRes;
    history.value = historyRes;
    myRating.value = leaderboard.me;
  } catch (e) {
    if (isAxiosError(e) && e.response?.status === 403) {
      accessDenied.value = true;
    } else {
      throw e;
    }
  } finally {
    loading.value = false;
  }
}

onMounted(load);

function toggleSubject(id: number) {
  const idx = selectedSubjectIds.value.indexOf(id);
  if (idx === -1) selectedSubjectIds.value.push(id);
  else selectedSubjectIds.value.splice(idx, 1);
}

function subjectCardClass(subject: EntSubject): string {
  if (selectedSubjectIds.value.includes(subject.id)) {
    return "border-moss bg-moss/10";
  }
  return "border-line bg-paper hover:border-moss/50";
}

async function handleStart() {
  if (!canStart.value) return;
  starting.value = true;
  startError.value = "";
  try {
    const simulation = await startEntSimulation({
      subject_ids: selectedSubjectIds.value,
      questions_per_subject: questionsPerSubject.value,
      is_timed: isTimed.value,
      duration_minutes: isTimed.value ? durationMinutes.value : undefined,
      language: examLanguage.value,
    });
    router.push(`/ent/${simulation.id}`);
  } catch (e) {
    // A short bank comes back as 422 naming the subject, the language and
    // the two numbers -- far more useful than anything this screen could
    // guess, so it is shown as the server wrote it.
    const detail = isAxiosError(e) ? e.response?.data?.detail : undefined;
    startError.value =
      typeof detail === "string"
        ? detail
        : "Не удалось начать симуляцию. Проверьте, что в выбранных предметах есть вопросы.";
  } finally {
    starting.value = false;
  }
}

function timingLabel(s: EntSimulationSummary): string {
  if (!s.is_timed) return "без таймера";
  return s.time_expired ? "время вышло" : "уложился в срок";
}

function historyPercent(s: EntSimulationSummary): number {
  return scorePercent(s.total_score ?? 0, s.max_score ?? 0);
}

const HISTORY_TONES: Record<string, string> = {
  success: "bg-green-600/15 text-green-700 dark:text-green-500",
  warning: "bg-amber-600/15 text-amber-700 dark:text-amber-500",
  danger: "bg-red-500/15 text-red-600 dark:text-red-400",
};

function historyTone(s: EntSimulationSummary): string {
  return HISTORY_TONES[scoreTone(historyPercent(s))];
}
</script>

<template>
  <PageContainer>
    <PageHeader title="ЕНТ-тренажёр" subtitle="Выберите предметы и режим прохождения, чтобы начать пробную симуляцию.">
      <template #actions>
        <router-link class="text-sm text-moss underline underline-offset-2 hover:opacity-70" to="/ent/leaderboard">
          Топ студентов
        </router-link>
      </template>
    </PageHeader>

    <div v-if="loading" class="space-y-6">
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div v-for="i in 6" :key="i" class="h-24 animate-pulse rounded-2xl bg-paper-2"></div>
      </div>
      <div class="h-52 w-full animate-pulse rounded-2xl bg-paper-2"></div>
      <div class="h-24 w-full animate-pulse rounded-2xl bg-paper-2"></div>
    </div>

    <div v-else-if="accessDenied" class="card p-4 text-sm">
      <p class="text-ink-2">
        ЕНТ-тренажёр доступен только после одобрения хотя бы одной заявки на курс.
      </p>
      <router-link class="mt-2 inline-block text-moss underline underline-offset-2 hover:opacity-70" to="/catalog">
        Перейти в каталог курсов
      </router-link>
    </div>

    <template v-else>
      <div class="space-y-8">
        <router-link
          v-if="myRating"
          to="/ent/leaderboard"
          class="card group flex items-center gap-4 p-4 transition-all duration-200 hover:border-moss/50 hover:shadow-md"
        >
          <span class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-moss/10 text-moss">
            <Trophy :size="24" :stroke-width="1.6" />
          </span>
          <div class="min-w-0 flex-1">
            <p class="text-xs uppercase tracking-wide text-ink-3">Ваше место в рейтинге</p>
            <p class="text-lg font-semibold text-ink">
              #{{ myRating.rank }}
              <span class="text-sm font-normal text-ink-2">
                · {{ myRating.simulations_completed }}
                {{ pluralRu(myRating.simulations_completed, ["попытка", "попытки", "попыток"]) }}
              </span>
            </p>
          </div>
          <span class="shrink-0 rounded-full bg-moss px-3 py-1.5 text-sm font-semibold text-moss-fg">
            {{ myRating.total_xp }} XP
          </span>
          <svg class="h-4 w-4 shrink-0 text-ink-3 transition-transform duration-200 group-hover:translate-x-1" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M7 4l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </router-link>

        <section class="card space-y-4 p-4">
          <div class="flex items-baseline justify-between gap-2">
            <p class="font-medium text-ink">Предметы</p>
            <p class="text-xs text-ink-3">
              Выбрано {{ selectedSubjectIds.length }} из {{ ENT_FULL_SUBJECT_COUNT }}
            </p>
          </div>

          <!-- One column only on the narrowest phones (~320px, where a 2-up
               grid leaves ~135px and "История Казахстана" wraps to three
               lines), two from 360px up, and four on a desktop so a full ЕНТ
               subject list stays on one row. -->
          <div class="grid grid-cols-1 gap-3 min-[360px]:grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
            <button
              v-for="subject in subjects"
              :key="subject.id"
              type="button"
              class="group relative flex flex-col items-center gap-2 rounded-2xl border p-4 text-center transition-all duration-200 ease-out hover:-translate-y-0.5 hover:shadow-md"
              :class="subjectCardClass(subject)"
              :aria-pressed="selectedSubjectIds.includes(subject.id)"
              @click="toggleSubject(subject.id)"
            >
              <span
                class="absolute right-2 top-2 flex h-5 w-5 items-center justify-center rounded-full transition-all duration-200"
                :class="
                  selectedSubjectIds.includes(subject.id)
                    ? 'scale-100 bg-moss text-moss-fg opacity-100'
                    : 'scale-50 opacity-0'
                "
              >
                <svg class="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
                  <path
                    fill-rule="evenodd"
                    d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
                    clip-rule="evenodd"
                  />
                </svg>
              </span>
              <span
                class="flex h-12 w-12 items-center justify-center rounded-xl transition-colors duration-200"
                :class="selectedSubjectIds.includes(subject.id) ? 'bg-moss/15 text-moss' : 'bg-paper-2 text-ink-2'"
              >
                <SubjectIcon :name="subject.name" class="h-6 w-6" />
              </span>
              <span class="text-sm font-medium text-ink">{{ capitalize(subject.name) }}</span>
              <span
                class="rounded-full px-2 py-0.5 text-[11px] font-medium transition-colors duration-200"
                :class="selectedSubjectIds.includes(subject.id) ? 'bg-moss/20 text-moss' : 'bg-paper-2 text-ink-2'"
              >
                {{ subject.question_count }} {{ pluralRu(subject.question_count, ["вопрос", "вопроса", "вопросов"]) }}
              </span>
            </button>
          </div>
          <p v-if="!subjects.length" class="text-sm text-ink-2">Предметы ещё не добавлены учителями.</p>
        </section>

        <section class="card space-y-5 p-4">
          <p class="font-medium text-ink">Язык сдачи</p>
          <div class="grid grid-cols-2 gap-3">
            <button
              v-for="language in EXAM_LANGUAGES"
              :key="language"
              type="button"
              class="flex flex-col items-center gap-1 rounded-2xl border p-4 text-center transition-colors duration-150"
              :class="
                examLanguage === language
                  ? 'border-moss bg-moss/10'
                  : 'border-line bg-paper hover:border-moss/50'
              "
              :aria-pressed="examLanguage === language"
              @click="examLanguage = language"
            >
              <LanguageChip :language="language" size="md" />
              <span class="text-sm font-medium text-ink">{{ LANGUAGE_LABEL[language] }}</span>
            </button>
          </div>
          <p class="text-xs text-ink-3">
            В симуляцию попадут только вопросы на выбранном языке.
          </p>

          <p class="font-medium text-ink">Параметры</p>

          <label class="block text-sm sm:w-1/2">
            <span class="mb-1.5 block font-medium text-ink-2">Вопросов на предмет</span>
            <input v-model.number="questionsPerSubject" type="number" min="1" max="50" class="input" />
          </label>

          <label class="flex items-center justify-between gap-3 rounded-xl border border-line p-3">
            <span class="flex flex-col">
              <span class="text-sm font-medium text-ink">Режим с таймером</span>
              <span class="text-xs text-ink-3">
                Экзаменационные условия — {{ durationLabel }} на {{ selectedSubjectIds.length || "…" }}
                {{ pluralRu(selectedSubjectIds.length, ["предмет", "предмета", "предметов"]) }}
              </span>
            </span>
            <input v-model="isTimed" type="checkbox" class="h-5 w-5 accent-moss" />
          </label>
          <span
            v-if="isTimed"
            class="inline-flex w-fit items-center gap-1.5 rounded-full bg-moss/10 px-3 py-1 text-xs font-medium text-moss"
          >
            <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
              <path d="M9 1 3.5 9H7l-1 6 5.5-8H8l1-6Z" />
            </svg>
            +20% XP за режим с таймером
          </span>
          <p v-else class="text-xs text-ink-3">
            Без ограничения по времени — попытка отметится как «без времени», бонус XP не начисляется.
          </p>

          <p v-if="startError" class="text-sm text-clay">{{ startError }}</p>
        </section>

        <!-- Everything that defines the attempt, restated in one place: the
             options above are spread across two cards, and this is the last
             chance to notice "1 предмет" when five were intended. -->
        <section class="card overflow-hidden">
          <div class="grid grid-cols-2 divide-x divide-line border-b border-line sm:grid-cols-4">
            <div class="p-3 text-center">
              <p class="text-[11px] uppercase tracking-wide text-ink-3">Предметов</p>
              <p class="mt-0.5 text-lg font-semibold tabular-nums text-ink">{{ selectedSubjectIds.length }}</p>
            </div>
            <div class="p-3 text-center">
              <p class="text-[11px] uppercase tracking-wide text-ink-3">Вопросов</p>
              <p class="mt-0.5 text-lg font-semibold tabular-nums text-ink">{{ totalQuestions || "—" }}</p>
            </div>
            <div class="border-t border-line p-3 text-center sm:border-t-0">
              <p class="text-[11px] uppercase tracking-wide text-ink-3">Время</p>
              <p class="mt-0.5 text-lg font-semibold text-ink">
                {{ !selectedSubjectIds.length ? "—" : isTimed ? durationLabel : "∞" }}
              </p>
            </div>
            <div class="border-t border-line p-3 text-center sm:border-t-0">
              <p class="text-[11px] uppercase tracking-wide text-ink-3">Язык</p>
              <p class="mt-0.5 flex justify-center"><LanguageChip :language="examLanguage" size="md" /></p>
            </div>
          </div>
          <div class="p-4">
            <BaseButton variant="cta" class="w-full" :disabled="!canStart || starting" @click="handleStart">
              {{ starting ? "Запускаем…" : "Начать симуляцию" }}
            </BaseButton>
            <p v-if="!canStart" class="mt-2 text-center text-xs text-ink-3">Выберите хотя бы один предмет</p>
          </div>
        </section>

        <section class="space-y-3">
          <p class="font-medium text-ink">История попыток</p>

          <div v-if="!history.length" class="card flex flex-col items-center gap-3 px-6 py-10 text-center">
            <span class="flex h-14 w-14 items-center justify-center rounded-full bg-moss/15 text-moss">
              <Trophy :size="28" :stroke-width="1.6" />
            </span>
            <p class="font-medium text-ink">Попыток пока не было</p>
            <p class="max-w-xs text-sm text-ink-2">Выберите предметы выше и начните первую симуляцию ЕНТ.</p>
          </div>

          <ul v-else class="space-y-2">
            <li v-for="s in history" :key="s.id">
              <router-link
                :to="`/ent/${s.id}`"
                class="card group flex items-center gap-3 p-3 text-sm transition-all duration-200 hover:border-moss/50 hover:shadow-md"
              >
                <!-- Score first: it is what the student is scanning the list
                     for, and the ring reads faster than "34/60". -->
                <span
                  v-if="s.status !== 'in_progress'"
                  class="flex h-11 w-11 shrink-0 flex-col items-center justify-center rounded-xl text-xs font-bold tabular-nums"
                  :class="historyTone(s)"
                >
                  {{ historyPercent(s) }}<span class="text-[9px] font-medium opacity-70">%</span>
                </span>
                <span
                  v-else
                  class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-amber-500/15 text-amber-700 dark:text-amber-500"
                  title="Попытка не завершена"
                >
                  <svg class="h-5 w-5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8">
                    <circle cx="10" cy="10" r="7.5" />
                    <path d="M10 5.5V10l3 2" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                </span>

                <span class="min-w-0 flex-1">
                  <span class="block truncate font-medium text-ink">
                    {{ s.status === "in_progress" ? "Не завершена" : `${s.total_score} / ${s.max_score} баллов` }}
                  </span>
                  <span class="block truncate text-xs text-ink-3">
                    {{ new Date(s.started_at).toLocaleString("ru-RU") }} · {{ timingLabel(s) }}
                  </span>
                </span>

                <span v-if="s.status !== 'in_progress'" class="shrink-0 rounded-full bg-moss/15 px-2.5 py-1 text-xs font-semibold text-moss">
                  +{{ s.xp_earned ?? 0 }} XP
                </span>
                <LanguageChip :language="s.language" />
                <svg
                  class="h-4 w-4 shrink-0 text-ink-3 transition-transform duration-200 group-hover:translate-x-1"
                  viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"
                >
                  <path d="M7 4l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              </router-link>
            </li>
          </ul>
        </section>
      </div>
    </template>
  </PageContainer>
</template>
