<script setup lang="ts">
import { onMounted, ref } from "vue";

import { listMyTeachingCategories } from "@/api/categories";
import type { Category } from "@/types";

const categories = ref<Category[]>([]);
const loading = ref(true);

onMounted(async () => {
  categories.value = await listMyTeachingCategories();
  loading.value = false;
});
</script>

<template>
  <div>
    <h1 class="mb-6 text-2xl font-semibold">Мои категории</h1>
    <p v-if="loading" class="text-fg/60">Загрузка…</p>
    <p v-else-if="!categories.length" class="text-fg/60">Вам пока не назначили ни одной категории.</p>
    <ul v-else class="space-y-3">
      <li v-for="category in categories" :key="category.id">
        <router-link
          :to="`/teacher/categories/${category.id}`"
          class="block rounded-xl border border-fg/10 p-4 hover:border-accent"
        >
          <p class="font-medium">{{ category.name }}</p>
          <p v-if="category.description" class="text-sm text-fg/60">{{ category.description }}</p>
        </router-link>
      </li>
    </ul>
  </div>
</template>
