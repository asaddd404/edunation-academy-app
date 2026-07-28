<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import { listSections } from "@/api/sections";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import type { Section } from "@/types";

const route = useRoute();
const categoryId = Number(route.params.id);

const sections = ref<Section[]>([]);
const loading = ref(true);
const error = ref("");

onMounted(async () => {
  try {
    sections.value = await listSections(categoryId);
  } catch {
    error.value = "Не удалось загрузить содержимое категории.";
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div>
    <h1 class="mb-6 text-2xl font-semibold">Содержимое курса</h1>
    <p v-if="loading" class="text-fg/60">Загрузка…</p>
    <p v-else-if="error" class="text-red-500">{{ error }}</p>
    <p v-else-if="!sections.length" class="text-fg/60">Разделы пока не добавлены.</p>
    <div v-else class="space-y-6">
      <div v-for="section in sections" :key="section.id" class="rounded-xl border border-fg/10 p-4">
        <h2 class="mb-3 text-lg font-medium">{{ section.title }}</h2>
        <ul class="space-y-2">
          <li v-for="lesson in section.lessons" :key="lesson.id">
            <router-link
              v-if="lesson.is_unlocked"
              :to="`/lessons/${lesson.id}`"
              class="flex items-center justify-between rounded-lg border border-fg/10 px-4 py-3 hover:border-accent"
            >
              <span>{{ lesson.title }}</span>
              <BaseBadge :tone="lesson.is_passed ? 'success' : 'neutral'">
                {{ lesson.is_passed ? "Пройден" : "Открыт" }}
              </BaseBadge>
            </router-link>
            <div v-else class="flex items-center justify-between rounded-lg border border-fg/10 px-4 py-3 opacity-50">
              <span>{{ lesson.title }}</span>
              <BaseBadge tone="neutral">Заблокирован</BaseBadge>
            </div>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
