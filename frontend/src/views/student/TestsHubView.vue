<script setup lang="ts">
import { Check, ClipboardList, Lock, Shuffle } from "@lucide/vue";
import { computed, onMounted, ref } from "vue";

import { listMyTests } from "@/api/tests";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { TestHubCourse, TestInfo } from "@/types";
import { pluralRu } from "@/utils/subjectTheme";

/** Every test of every course the student is enrolled in, in course order. */
const courses = ref<TestHubCourse[]>([]);
const loading = ref(true);
const loadError = ref("");

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    courses.value = await listMyTests();
  } catch {
    loadError.value = "Не удалось загрузить тесты.";
  } finally {
    loading.value = false;
  }
}

onMounted(load);

const totals = computed(() => {
  const all = courses.value.flatMap((c) =>
    c.sections.flatMap((s) => [...s.lesson_tests, ...(s.section_test ? [s.section_test] : [])]),
  );
  return { all: all.length, passed: all.filter((t) => t.is_passed).length };
});

function link(test: TestInfo): string {
  return test.kind === "lesson" ? `/lessons/${test.id}` : `/sections/${test.id}/test`;
}

function status(test: TestInfo): { label: string; tone: "success" | "warning" | "neutral" } {
  if (test.is_passed) return { label: "Пройден", tone: "success" };
  if (!test.is_unlocked) return { label: "Заблокирован", tone: "neutral" };
  if (test.in_progress_attempt_id) return { label: "Начат", tone: "warning" };
  return { label: "Доступен", tone: "warning" };
}

function details(test: TestInfo): string {
  const parts = [`${test.question_count} ${pluralRu(test.question_count, ["вопрос", "вопроса", "вопросов"])}`];
  if (test.attempts_used) {
    parts.push(`${test.attempts_used} ${pluralRu(test.attempts_used, ["попытка", "попытки", "попыток"])}`);
  }
  if (test.best_score !== null) parts.push(`лучший ${test.best_score}%`);
  return parts.join(" · ");
}
</script>

<template>
  <PageContainer>
    <PageHeader title="Тесты">
      <template #subtitle>
        Мини-тесты уроков и итоговые тесты разделов ваших курсов.
        <template v-if="totals.all"> Пройдено {{ totals.passed }} из {{ totals.all }}.</template>
      </template>
    </PageHeader>

    <div v-if="loading" class="space-y-4">
      <div v-for="n in 2" :key="n" class="h-40 animate-pulse rounded-2xl bg-paper-2" />
    </div>

    <div v-else-if="loadError" class="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-center">
      <p class="text-clay">{{ loadError }}</p>
      <BaseButton variant="secondary" @click="load">Повторить</BaseButton>
    </div>

    <div v-else-if="!courses.length" class="card flex flex-col items-center gap-3 px-6 py-12 text-center">
      <span class="flex h-14 w-14 items-center justify-center rounded-full bg-moss/15 text-moss">
        <ClipboardList :size="28" :stroke-width="1.6" />
      </span>
      <p class="font-medium text-ink">Пока нет доступных тестов</p>
      <p class="max-w-sm text-sm text-ink-2">
        Тесты появятся здесь, когда вас запишут на курс и учитель добавит вопросы к урокам.
      </p>
      <router-link to="/catalog" class="btn-primary">Перейти в каталог</router-link>
    </div>

    <div v-else class="space-y-6">
      <section v-for="course in courses" :key="course.category_id" class="card space-y-4 p-4">
        <h2 class="font-display text-xl font-semibold text-ink">{{ course.category_name }}</h2>

        <div v-for="section in course.sections" :key="section.section_id" class="space-y-2">
          <h3 class="text-sm font-semibold uppercase tracking-wide text-ink-3">{{ section.title }}</h3>
          <ul class="space-y-2">
            <li
              v-for="test in [...section.lesson_tests, ...(section.section_test ? [section.section_test] : [])]"
              :key="`${test.kind}-${test.id}`"
            >
              <component
                :is="test.is_unlocked ? 'router-link' : 'div'"
                :to="test.is_unlocked ? link(test) : undefined"
                class="flex items-center gap-3 rounded-xl border border-line p-3 text-sm transition-colors"
                :class="test.is_unlocked ? 'hover:border-moss/40 hover:bg-paper-2' : 'opacity-60'"
              >
                <Lock v-if="!test.is_unlocked" :size="18" :stroke-width="1.8" class="shrink-0 text-ink-3" />
                <Check v-else-if="test.is_passed" :size="18" :stroke-width="2.2" class="shrink-0 text-moss" />
                <ClipboardList v-else :size="18" :stroke-width="1.8" class="shrink-0 text-moss" />
                <span class="min-w-0 flex-1">
                  <span class="block truncate font-medium text-ink">
                    {{ test.kind === "section" ? "Итоговый тест раздела" : test.title }}
                  </span>
                  <span class="flex flex-wrap items-center gap-x-1.5 text-xs text-ink-3">
                    <span>{{ details(test) }}</span>
                    <span v-if="test.pool_size > test.question_count" class="inline-flex items-center gap-1 text-moss">
                      <Shuffle :size="12" :stroke-width="2" /> вопросы меняются
                    </span>
                  </span>
                </span>
                <BaseBadge :tone="status(test).tone">{{ status(test).label }}</BaseBadge>
              </component>
            </li>
          </ul>
        </div>
      </section>
    </div>
  </PageContainer>
</template>
