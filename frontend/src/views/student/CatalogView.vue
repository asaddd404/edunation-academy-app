<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { getCategoryImageUrl } from "@/api/categories";
import ApplicationStatusBadge from "@/components/application/ApplicationStatusBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import { useApplicationsStore } from "@/stores/applications";
import { useCategoriesStore } from "@/stores/categories";
import { capitalize, pluralRu, subjectTheme } from "@/utils/subjectTheme";

const categories = useCategoriesStore();
const applications = useApplicationsStore();
const applyingId = ref<number | null>(null);
const search = ref("");
const activeTag = ref<string | null>(null);

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

function lessonsLabel(count: number): string {
  return `${count} ${pluralRu(count, ["урок", "урока", "уроков"])}`;
}

function hoursLabel(seconds: number): string | null {
  if (!seconds) return null;
  const hours = Math.max(1, Math.round(seconds / 3600));
  return `${hours} ${pluralRu(hours, ["час", "часа", "часов"])}`;
}

const tags = computed(() => {
  const names = [...new Set(categories.list.map((c) => capitalize(c.name)))].sort((a, b) => a.localeCompare(b, "ru"));
  return names.slice(0, 8);
});

const filtered = computed(() => {
  const query = search.value.trim().toLowerCase();
  return categories.list.filter((c) => {
    const matchesTag = !activeTag.value || capitalize(c.name) === activeTag.value;
    const matchesQuery = !query || c.name.toLowerCase().includes(query) || (c.description ?? "").toLowerCase().includes(query);
    return matchesTag && matchesQuery;
  });
});
</script>

<template>
  <div>
    <div class="relative mb-8 overflow-hidden rounded-2xl border border-border bg-card px-6 py-10 sm:px-10">
      <div class="glow-blob -left-16 -top-24 h-64 w-64" />
      <div class="glow-blob -bottom-24 -right-10 h-64 w-64" style="background: radial-gradient(circle, hsl(330 81% 60% / 0.5), transparent 70%)" />
      <div class="relative">
        <h1 class="text-3xl font-bold sm:text-4xl">
          <span class="text-gradient-brand">Каталог предметов</span>
        </h1>
        <p class="mt-2 max-w-xl text-sm text-fg/60 sm:text-base">
          Выбирай предмет, подавай заявку и открывай уроки, тесты и симуляции ЕНТ — всё в одном месте.
        </p>

        <div class="mt-6 flex flex-col gap-3">
          <input
            v-model="search"
            type="search"
            placeholder="Найти предмет…"
            class="w-full max-w-md rounded-xl border border-fg/20 bg-transparent px-4 py-3 text-sm text-fg placeholder:text-fg/40 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 sm:bg-bg/60"
          />
          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              class="rounded-full border px-3.5 py-1.5 text-xs font-medium transition-all duration-150"
              :class="
                activeTag === null
                  ? 'border-transparent bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-500/25'
                  : 'border-border text-fg/70 hover:border-indigo-500/40 hover:text-fg'
              "
              @click="activeTag = null"
            >
              Все
            </button>
            <button
              v-for="tag in tags"
              :key="tag"
              type="button"
              class="rounded-full border px-3.5 py-1.5 text-xs font-medium transition-all duration-150"
              :class="
                activeTag === tag
                  ? 'border-transparent bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-500/25'
                  : 'border-border text-fg/70 hover:border-indigo-500/40 hover:text-fg'
              "
              @click="activeTag = activeTag === tag ? null : tag"
            >
              {{ tag }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <p v-if="categories.loading" class="text-fg/60">Загрузка…</p>
    <p v-else-if="!filtered.length" class="text-fg/60">Ничего не найдено по вашему запросу.</p>
    <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <div
        v-for="category in filtered"
        :key="category.id"
        class="flex flex-col overflow-hidden rounded-2xl border border-border bg-card transition-all duration-200 hover:-translate-y-0.5 hover:shadow-xl hover:shadow-indigo-500/5"
      >
        <img
          v-if="category.has_image"
          :src="getCategoryImageUrl(category.id)"
          alt=""
          class="h-32 w-full object-cover"
        />
        <div
          v-else
          class="flex h-32 w-full items-center justify-center bg-gradient-to-br text-5xl"
          :class="subjectTheme(category.name, category.id).gradient"
        >
          {{ subjectTheme(category.name, category.id).icon }}
        </div>

        <div class="flex flex-1 flex-col gap-3 p-5">
          <div class="flex items-start justify-between gap-2">
            <h2 class="text-lg font-semibold">{{ capitalize(category.name) }}</h2>
            <ApplicationStatusBadge :status="category.my_application_status" />
          </div>
          <p v-if="category.description" class="line-clamp-2 text-sm text-fg/60">{{ category.description }}</p>

          <div class="flex flex-wrap gap-1.5 text-xs">
            <span class="rounded-full bg-fg/5 px-2.5 py-1 font-medium text-fg/70">
              {{ lessonsLabel(category.lesson_count) }}
            </span>
            <span v-if="hoursLabel(category.total_duration_seconds)" class="rounded-full bg-fg/5 px-2.5 py-1 font-medium text-fg/70">
              ~{{ hoursLabel(category.total_duration_seconds) }}
            </span>
          </div>

          <router-link v-if="category.my_application_status === 'approved'" :to="`/categories/${category.id}`" class="mt-auto">
            <BaseButton class="w-full">Открыть</BaseButton>
          </router-link>
          <BaseButton
            v-else
            variant="cta"
            class="mt-auto w-full"
            :disabled="category.my_application_status === 'pending' || applyingId === category.id"
            @click="handleApply(category.id)"
          >
            Подать заявку
          </BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>
