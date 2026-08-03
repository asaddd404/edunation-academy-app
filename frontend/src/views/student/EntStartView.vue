<script setup lang="ts">
import { isAxiosError } from "axios";
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { getEntLeaderboard, listEntSimulations, listEntSubjects, startEntSimulation } from "@/api/ent";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { EntLeaderboardEntry, EntSimulationSummary, EntSubject, ExamLanguage } from "@/types";
import { EXAM_LANGUAGES, LANGUAGE_FLAG, LANGUAGE_LABEL } from "@/utils/examLanguage";
import { capitalize, pluralRu, subjectTheme } from "@/utils/subjectTheme";

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
const durationMinutes = ref(60);

const canStart = computed(
  () =>
    selectedSubjectIds.value.length > 0 &&
    questionsPerSubject.value >= 1 &&
    (!isTimed.value || (durationMinutes.value >= 1 && durationMinutes.value <= 240)),
);

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
    return `border-transparent bg-gradient-to-br ${subjectTheme(subject.name, subject.id).gradient} scale-[1.02] text-white shadow-lg shadow-indigo-500/20`;
  }
  return "border-border bg-card hover:border-indigo-500/40";
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

function statusLabel(s: EntSimulationSummary): string {
  if (s.status === "in_progress") return "В процессе";
  const timing = s.is_timed ? (s.time_expired ? "со временем, не уложился" : "со временем, уложился") : "без времени";
  return `${s.total_score}/${s.max_score} · ${timing} · +${s.xp_earned ?? 0} XP`;
}
</script>

<template>
  <div class="mx-auto max-w-2xl space-y-8">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h1 class="mb-2 text-2xl font-semibold">
          <span class="text-gradient-brand">ЕНТ-тренажёр</span>
        </h1>
        <p class="text-sm text-fg/60">Выберите предметы и режим прохождения, чтобы начать пробную симуляцию.</p>
      </div>
      <router-link class="shrink-0 text-sm text-accent underline underline-offset-2 hover:opacity-70" to="/ent/leaderboard">
        Топ студентов
      </router-link>
    </div>

    <p v-if="loading" class="text-fg/60">Загрузка…</p>

    <div v-else-if="accessDenied" class="glass-card p-4 text-sm">
      <p class="text-fg/80">
        ЕНТ-тренажёр доступен только после одобрения хотя бы одной заявки на курс.
      </p>
      <router-link class="mt-2 inline-block text-accent underline underline-offset-2 hover:opacity-70" to="/catalog">
        Перейти в каталог курсов
      </router-link>
    </div>

    <template v-else>
      <div v-if="myRating" class="glass-card flex items-center justify-between p-4 text-sm">
        <span class="text-fg/60">Ваш рейтинг</span>
        <div class="flex items-center gap-3">
          <span>#{{ myRating.rank }}</span>
          <span class="rounded-full bg-pop px-2.5 py-1 text-xs font-semibold text-black">{{ myRating.total_xp }} XP</span>
          <span class="text-fg/60">{{ myRating.simulations_completed }} попыток</span>
        </div>
      </div>

      <section class="glass-card space-y-4 p-4">
        <p class="font-medium">Предметы</p>
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <button
            v-for="subject in subjects"
            :key="subject.id"
            type="button"
            class="relative flex flex-col items-center gap-1.5 rounded-2xl border p-4 text-center transition-all duration-150"
            :class="subjectCardClass(subject)"
            @click="toggleSubject(subject.id)"
          >
            <svg
              v-if="selectedSubjectIds.includes(subject.id)"
              class="absolute right-2 top-2 h-4 w-4"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fill-rule="evenodd"
                d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
                clip-rule="evenodd"
              />
            </svg>
            <span class="text-2xl">{{ subjectTheme(subject.name, subject.id).icon }}</span>
            <span class="text-sm font-medium">{{ capitalize(subject.name) }}</span>
            <span
              class="rounded-full px-2 py-0.5 text-[11px] font-medium"
              :class="selectedSubjectIds.includes(subject.id) ? 'bg-white/20 text-white' : 'bg-fg/10 text-fg/60'"
            >
              {{ subject.question_count }} {{ pluralRu(subject.question_count, ["вопрос", "вопроса", "вопросов"]) }}
            </span>
          </button>
        </div>
        <p v-if="!subjects.length" class="text-sm text-fg/60">Предметы ещё не добавлены учителями.</p>
      </section>

      <section class="glass-card space-y-5 p-4">
        <p class="font-medium">Язык сдачи</p>
        <div class="grid grid-cols-2 gap-3">
          <button
            v-for="language in EXAM_LANGUAGES"
            :key="language"
            type="button"
            class="flex flex-col items-center gap-1 rounded-2xl border p-4 text-center transition-all duration-150"
            :class="
              examLanguage === language
                ? 'scale-[1.02] border-transparent bg-gradient-to-br from-indigo-600 to-violet-600 text-white shadow-lg shadow-indigo-500/20'
                : 'border-border bg-card hover:border-indigo-500/40'
            "
            :aria-pressed="examLanguage === language"
            @click="examLanguage = language"
          >
            <span class="text-2xl">{{ LANGUAGE_FLAG[language] }}</span>
            <span class="text-sm font-medium">{{ LANGUAGE_LABEL[language] }}</span>
          </button>
        </div>
        <p class="text-xs text-fg/50">
          В симуляцию попадут только вопросы на выбранном языке.
        </p>

        <p class="font-medium">Параметры</p>

        <div class="grid gap-4 sm:grid-cols-2">
          <label class="block text-sm">
            <span class="mb-1.5 block font-medium text-fg/80">Вопросов на предмет</span>
            <input
              v-model.number="questionsPerSubject"
              type="number"
              min="1"
              max="50"
              class="w-full rounded-xl border border-fg/20 bg-transparent px-4 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
            />
          </label>
          <label v-if="isTimed" class="block text-sm">
            <span class="mb-1.5 block font-medium text-fg/80">Время (минут)</span>
            <input
              v-model.number="durationMinutes"
              type="number"
              min="1"
              max="240"
              class="w-full rounded-xl border border-fg/20 bg-transparent px-4 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
            />
          </label>
        </div>

        <label class="flex items-center justify-between gap-3 rounded-xl border border-border p-3">
          <span class="flex flex-col">
            <span class="text-sm font-medium">Режим с таймером</span>
            <span class="text-xs text-fg/50">Экзаменационные условия — уложитесь в лимит времени</span>
          </span>
          <input v-model="isTimed" type="checkbox" class="h-5 w-5 accent-indigo-600" />
        </label>
        <span
          v-if="isTimed"
          class="inline-flex w-fit items-center gap-1 rounded-full border border-amber-500/25 bg-gradient-to-r from-amber-500/15 to-orange-500/10 px-3 py-1 text-xs font-medium text-amber-700 dark:text-amber-400"
        >
          🔥 +20% XP за режим с таймером
        </span>
        <p v-else class="text-xs text-fg/50">
          Без ограничения по времени — попытка отметится как «без времени», бонус XP не начисляется.
        </p>

        <p v-if="startError" class="text-sm text-red-600 dark:text-red-500">{{ startError }}</p>
        <BaseButton variant="cta" class="w-full" :disabled="!canStart || starting" @click="handleStart">Начать симуляцию</BaseButton>
      </section>

      <section class="space-y-3">
        <p class="font-medium">История попыток</p>

        <div v-if="!history.length" class="glass-card flex flex-col items-center gap-3 px-6 py-10 text-center">
          <div class="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-2xl shadow-lg shadow-indigo-500/20">
            🏆
          </div>
          <p class="font-medium">Попыток пока не было</p>
          <p class="max-w-xs text-sm text-fg/60">Выберите предметы выше и начните первую симуляцию ЕНТ.</p>
        </div>

        <ul v-else class="space-y-2">
          <li
            v-for="s in history"
            :key="s.id"
            class="flex items-center justify-between rounded-xl border border-border bg-card p-3 text-sm transition-all duration-200 hover:scale-[1.01]"
          >
            <span>{{ new Date(s.started_at).toLocaleString("ru-RU") }}</span>
            <div class="flex items-center gap-2">
              <BaseBadge tone="neutral" :title="LANGUAGE_LABEL[s.language]">{{ LANGUAGE_FLAG[s.language] }}</BaseBadge>
              <BaseBadge :tone="s.status === 'in_progress' ? 'warning' : 'neutral'">{{ statusLabel(s) }}</BaseBadge>
              <router-link class="text-accent underline underline-offset-2 hover:opacity-70" :to="`/ent/${s.id}`">Открыть</router-link>
            </div>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>
