<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import { getEntLeaderboard, listEntSimulations, listEntSubjects, startEntSimulation } from "@/api/ent";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { EntLeaderboardEntry, EntSimulationSummary, EntSubject } from "@/types";

const router = useRouter();

const subjects = ref<EntSubject[]>([]);
const history = ref<EntSimulationSummary[]>([]);
const myRating = ref<EntLeaderboardEntry | null>(null);
const loading = ref(true);
const starting = ref(false);
const startError = ref("");

const selectedSubjectIds = ref<number[]>([]);
const questionsPerSubject = ref(10);
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
  const [subjectsRes, historyRes, leaderboard] = await Promise.all([
    listEntSubjects(),
    listEntSimulations(),
    getEntLeaderboard(1),
  ]);
  subjects.value = subjectsRes;
  history.value = historyRes;
  myRating.value = leaderboard.me;
  loading.value = false;
}

onMounted(load);

function toggleSubject(id: number) {
  const idx = selectedSubjectIds.value.indexOf(id);
  if (idx === -1) selectedSubjectIds.value.push(id);
  else selectedSubjectIds.value.splice(idx, 1);
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
    });
    router.push(`/ent/${simulation.id}`);
  } catch {
    startError.value = "Не удалось начать симуляцию. Проверьте, что в выбранных предметах есть вопросы.";
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
        <h1 class="mb-2 text-2xl font-semibold">ЕНТ-тренажёр</h1>
        <p class="text-sm text-fg/60">Выберите предметы и режим прохождения, чтобы начать пробную симуляцию.</p>
      </div>
      <router-link class="shrink-0 text-sm text-accent hover:underline" to="/ent/leaderboard">
        🏆 Топ студентов
      </router-link>
    </div>

    <p v-if="loading" class="text-fg/60">Загрузка…</p>

    <template v-else>
      <div v-if="myRating" class="flex items-center justify-between rounded-xl border border-fg/10 p-4 text-sm">
        <span class="text-fg/60">Ваш рейтинг</span>
        <div class="flex items-center gap-3">
          <span>#{{ myRating.rank }}</span>
          <span class="font-medium">{{ myRating.total_xp }} XP</span>
          <span class="text-fg/60">{{ myRating.simulations_completed }} попыток</span>
        </div>
      </div>
      <section class="space-y-4 rounded-xl border border-fg/10 p-4">
        <p class="font-medium">Предметы</p>
        <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <label
            v-for="subject in subjects"
            :key="subject.id"
            class="flex items-center gap-2 rounded-lg border border-fg/10 px-3 py-2 text-sm"
          >
            <input
              type="checkbox"
              :checked="selectedSubjectIds.includes(subject.id)"
              @change="toggleSubject(subject.id)"
            />
            {{ subject.name }}
            <span class="ml-auto text-fg/50">{{ subject.question_count }}</span>
          </label>
        </div>
        <p v-if="!subjects.length" class="text-sm text-fg/60">Предметы ещё не добавлены учителями.</p>

        <label class="block text-sm">
          <span class="mb-1.5 block font-medium text-fg/80">Вопросов на предмет</span>
          <input
            v-model.number="questionsPerSubject"
            type="number"
            min="1"
            max="50"
            class="w-32 rounded-lg border border-fg/20 bg-transparent px-4 py-2.5 text-sm"
          />
        </label>

        <div class="space-y-2">
          <label class="flex items-center gap-2 text-sm font-medium">
            <input type="checkbox" v-model="isTimed" />
            Прохождение с ограничением по времени
          </label>
          <label v-if="isTimed" class="block text-sm">
            <span class="mb-1.5 block font-medium text-fg/80">Время (минут)</span>
            <input
              v-model.number="durationMinutes"
              type="number"
              min="1"
              max="240"
              class="w-32 rounded-lg border border-fg/20 bg-transparent px-4 py-2.5 text-sm"
            />
          </label>
          <p v-else class="text-sm text-fg/60">Без ограничения по времени — статус попытки отметится как "без времени".</p>
        </div>

        <p v-if="startError" class="text-sm text-red-500">{{ startError }}</p>
        <BaseButton :disabled="!canStart || starting" @click="handleStart">Начать симуляцию</BaseButton>
      </section>

      <section class="space-y-3">
        <p class="font-medium">История попыток</p>
        <ul v-if="history.length" class="space-y-2">
          <li
            v-for="s in history"
            :key="s.id"
            class="flex items-center justify-between rounded-lg border border-fg/10 p-3 text-sm"
          >
            <span>{{ new Date(s.started_at).toLocaleString("ru-RU") }}</span>
            <div class="flex items-center gap-2">
              <BaseBadge :tone="s.status === 'in_progress' ? 'warning' : 'neutral'">{{ statusLabel(s) }}</BaseBadge>
              <router-link class="text-accent hover:underline" :to="`/ent/${s.id}`">Открыть</router-link>
            </div>
          </li>
        </ul>
        <p v-else class="text-sm text-fg/60">Попыток пока не было.</p>
      </section>
    </template>
  </div>
</template>
