<script setup lang="ts">
import { onMounted, ref } from "vue";

import { getCategoryImageUrl } from "@/api/categories";
import ApplicationStatusBadge from "@/components/application/ApplicationStatusBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import { useApplicationsStore } from "@/stores/applications";
import { useCategoriesStore } from "@/stores/categories";

const categories = useCategoriesStore();
const applications = useApplicationsStore();
const applyingId = ref<number | null>(null);

onMounted(() => categories.fetchAll());

async function handleApply(categoryId: number) {
  applyingId.value = categoryId;
  try {
    const application = await applications.apply(categoryId);
    const category = categories.list.find((c) => c.id === categoryId);
    if (category) category.my_application_status = application.status;
  } finally {
    applyingId.value = null;
  }
}
</script>

<template>
  <div>
    <h1 class="mb-6 text-2xl font-semibold">Каталог предметов</h1>
    <p v-if="categories.loading" class="text-fg/60">Загрузка…</p>
    <div v-else class="grid gap-4 sm:grid-cols-2">
      <div
        v-for="category in categories.list"
        :key="category.id"
        class="flex flex-col gap-3 rounded-xl border border-fg/10 p-5"
      >
        <img
          v-if="category.has_image"
          :src="getCategoryImageUrl(category.id)"
          alt=""
          class="-mx-5 -mt-5 mb-1 h-32 rounded-t-xl object-cover"
        />
        <div class="flex items-start justify-between gap-2">
          <h2 class="text-lg font-medium">{{ category.name }}</h2>
          <ApplicationStatusBadge :status="category.my_application_status" />
        </div>
        <p v-if="category.description" class="text-sm text-fg/60">{{ category.description }}</p>
        <router-link v-if="category.my_application_status === 'approved'" :to="`/categories/${category.id}`" class="mt-auto">
          <BaseButton class="w-full">Открыть</BaseButton>
        </router-link>
        <BaseButton
          v-else
          class="mt-auto"
          :disabled="category.my_application_status === 'pending' || applyingId === category.id"
          @click="handleApply(category.id)"
        >
          Подать заявку
        </BaseButton>
      </div>
    </div>
  </div>
</template>
