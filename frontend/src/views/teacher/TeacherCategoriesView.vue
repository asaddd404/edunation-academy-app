<script setup lang="ts">
import { BookOpen, ChevronRight } from "@lucide/vue";
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
      <BookOpen :size="30" :stroke-width="1.6" class="text-ink-3" />
      <p class="mt-3 text-ink-2">Вам пока не назначили ни одной категории — обратитесь к администратору.</p>
    </div>

    <ul v-else class="grid gap-3 lg:grid-cols-2">
      <li v-for="category in categories" :key="category.id">
        <!-- Looked like plain text before; the arrow and lift say "opens". -->
        <router-link
          :to="`/teacher/categories/${category.id}`"
          class="card group flex h-full items-center gap-4 p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-moss/40 hover:shadow-md"
        >
          <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-moss/10 text-moss">
            <BookOpen :size="20" :stroke-width="1.8" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block font-medium text-ink">{{ category.name }}</span>
            <span v-if="category.description" class="mt-0.5 line-clamp-2 block text-sm text-ink-2">
              {{ category.description }}
            </span>
          </span>
          <ChevronRight
            :size="18"
            class="shrink-0 text-ink-3 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-moss"
          />
        </router-link>
      </li>
    </ul>
  </PageContainer>
</template>
