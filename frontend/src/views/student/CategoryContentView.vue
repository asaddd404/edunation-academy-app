<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import { listSections } from "@/api/sections";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { Section } from "@/types";

const route = useRoute();
const categoryId = Number(route.params.id);

const sections = ref<Section[]>([]);
const loading = ref(true);
const error = ref("");

async function load() {
  loading.value = true;
  error.value = "";
  try {
    sections.value = await listSections(categoryId);
  } catch {
    error.value = "Не удалось загрузить содержимое категории.";
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <PageContainer>
    <PageHeader title="Содержимое курса" />

    <div v-if="loading" class="space-y-6">
      <div v-for="n in 3" :key="n" class="h-40 animate-pulse rounded-xl bg-paper-2" />
    </div>
    <div v-else-if="error" class="card flex flex-col items-center gap-3 px-6 py-12 text-center">
      <p class="text-sm text-clay">{{ error }}</p>
      <BaseButton variant="secondary" @click="load">Повторить</BaseButton>
    </div>
    <p v-else-if="!sections.length" class="text-ink-2">Разделы пока не добавлены.</p>
    <div v-else class="space-y-6">
      <div v-for="section in sections" :key="section.id" class="card p-4">
        <h2 class="mb-3 text-lg font-medium text-ink">{{ section.title }}</h2>
        <ul class="space-y-2">
          <li v-for="lesson in section.lessons" :key="lesson.id">
            <router-link
              v-if="lesson.is_unlocked"
              :to="`/lessons/${lesson.id}`"
              class="flex items-center justify-between rounded-xl border border-line px-4 py-3 transition-colors hover:border-moss/50"
            >
              <span class="text-ink">{{ lesson.title }}</span>
              <BaseBadge :tone="lesson.is_passed ? 'success' : 'neutral'">
                {{ lesson.is_passed ? "Пройден" : "Открыт" }}
              </BaseBadge>
            </router-link>
            <div v-else class="flex items-center justify-between rounded-xl border border-line px-4 py-3 opacity-50">
              <span class="text-ink">{{ lesson.title }}</span>
              <BaseBadge tone="neutral">Заблокирован</BaseBadge>
            </div>
          </li>
          <li v-if="section.has_test">
            <router-link
              v-if="section.is_test_unlocked"
              :to="`/sections/${section.id}/test`"
              class="flex items-center justify-between rounded-xl border border-moss/40 px-4 py-3 transition-colors hover:border-moss/50"
            >
              <span class="text-ink">Тест раздела</span>
              <BaseBadge :tone="section.is_test_passed ? 'success' : 'neutral'">
                {{ section.is_test_passed ? "Пройден" : "Открыт" }}
              </BaseBadge>
            </router-link>
            <div v-else class="flex items-center justify-between rounded-xl border border-line px-4 py-3 opacity-50">
              <span class="text-ink">Тест раздела</span>
              <BaseBadge tone="neutral">Заблокирован</BaseBadge>
            </div>
          </li>
        </ul>
      </div>
    </div>
  </PageContainer>
</template>
