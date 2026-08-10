<script setup lang="ts">
import { onMounted, ref } from "vue";

import { listMyTeachingCategories } from "@/api/categories";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import type { Category } from "@/types";

const categories = ref<Category[]>([]);
const loading = ref(true);

onMounted(async () => {
  categories.value = await listMyTeachingCategories();
  loading.value = false;
});
</script>

<template>
  <PageContainer>
    <PageHeader title="Мои категории" />

    <div v-if="loading" class="space-y-3">
      <div v-for="i in 3" :key="i" class="h-20 animate-pulse rounded-xl bg-paper-2" />
    </div>

    <div v-else-if="!categories.length" class="card py-12 text-center">
      <p class="text-3xl">📚</p>
      <p class="mt-3 text-ink-2">Вам пока не назначили ни одной категории — обратитесь к администратору.</p>
    </div>

    <ul v-else class="space-y-3">
      <li v-for="category in categories" :key="category.id">
        <router-link
          :to="`/teacher/categories/${category.id}`"
          class="card block p-4 hover:border-line-strong"
        >
          <p class="font-medium text-ink">{{ category.name }}</p>
          <p v-if="category.description" class="text-sm text-ink-2">{{ category.description }}</p>
        </router-link>
      </li>
    </ul>
  </PageContainer>
</template>
