<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import { getSectionTest, startSectionTest } from "@/api/sections";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import CourseTestPanel from "@/components/test/CourseTestPanel.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { SectionTest } from "@/types";

const route = useRoute();
const sectionId = Number(route.params.id);

const test = ref<SectionTest | null>(null);
const loading = ref(true);
const loadError = ref("");

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    test.value = await getSectionTest(sectionId);
  } catch {
    loadError.value = "Тест раздела недоступен — возможно, пройдены не все уроки.";
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <PageContainer>
    <div v-if="loading" class="space-y-6">
      <div class="h-8 w-2/3 animate-pulse rounded-lg bg-paper-2"></div>
      <div class="h-64 w-full max-w-[42rem] animate-pulse rounded-2xl bg-paper-2"></div>
    </div>

    <div v-else-if="loadError" class="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-center">
      <p class="text-clay">{{ loadError }}</p>
      <BaseButton variant="secondary" @click="load">Повторить</BaseButton>
    </div>

    <template v-else-if="test">
      <PageHeader title="Тест раздела">
        <template #actions>
          <BaseBadge :tone="test.is_passed ? 'success' : 'neutral'">
            {{ test.is_passed ? "Пройден" : "Не пройден" }}
          </BaseBadge>
        </template>
      </PageHeader>

      <div class="max-w-[42rem]">
        <CourseTestPanel
          v-if="test.question_count"
          title="Итоговый тест"
          :question-count="test.question_count"
          :is-passed="test.is_passed"
          :start="() => startSectionTest(sectionId)"
          :leaderboard-to="{ path: '/leaderboard', query: { section: sectionId } }"
          @passed="test.is_passed = true"
        />
        <p v-else class="card p-4 text-sm text-ink-2">В этом разделе ещё нет теста.</p>
      </div>
    </template>
  </PageContainer>
</template>
