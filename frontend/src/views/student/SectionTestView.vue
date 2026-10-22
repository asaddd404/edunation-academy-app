<script setup lang="ts">
import { isAxiosError } from "axios";
import { Lock } from "@lucide/vue";
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
/** 403: the test is locked until every lesson in the section is passed --
 * retrying cannot help, so the page says what to do instead. */
const locked = ref(false);

async function load() {
  loading.value = true;
  loadError.value = "";
  locked.value = false;
  try {
    test.value = await getSectionTest(sectionId);
  } catch (e) {
    if (isAxiosError(e) && e.response?.status === 403) locked.value = true;
    else loadError.value = "Не удалось загрузить тест раздела.";
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

    <div v-else-if="locked" class="card mx-auto flex max-w-md flex-col items-center gap-3 px-6 py-10 text-center">
      <span class="flex h-12 w-12 items-center justify-center rounded-full bg-moss/10 text-moss">
        <Lock :size="22" :stroke-width="1.8" />
      </span>
      <p class="font-medium text-ink">Тест раздела пока закрыт</p>
      <p class="text-sm text-ink-2">Он откроется, когда вы пройдёте мини-тесты всех уроков этого раздела.</p>
      <router-link to="/catalog" class="btn-primary">К урокам</router-link>
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
