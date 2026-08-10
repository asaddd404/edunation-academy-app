<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { getCategoryImageUrl } from "@/api/categories";
import ApplicationStatusBadge from "@/components/application/ApplicationStatusBadge.vue";
import PageContainer from "@/components/layout/PageContainer.vue";
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
  <PageContainer>
    <div class="mb-8 overflow-hidden rounded-2xl border border-line bg-paper px-6 py-10 sm:px-10">
      <h1 class="font-display text-display-lg text-ink">Каталог предметов</h1>
      <p class="mt-2 max-w-xl text-sm text-ink-2 sm:text-base">
        Выбирай предмет, подавай заявку и открывай уроки, тесты и симуляции ЕНТ — всё в одном месте.
      </p>

      <div class="mt-6 flex flex-col gap-3">
        <input v-model="search" type="search" placeholder="Найти предмет…" class="input w-full max-w-md" />
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors"
            :class="
              activeTag === null
                ? 'border-transparent bg-moss text-moss-fg'
                : 'border-line text-ink-2 hover:border-line-strong hover:text-ink'
            "
            @click="activeTag = null"
          >
            Все
          </button>
          <button
            v-for="tag in tags"
            :key="tag"
            type="button"
            class="rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors"
            :class="
              activeTag === tag
                ? 'border-transparent bg-moss text-moss-fg'
                : 'border-line text-ink-2 hover:border-line-strong hover:text-ink'
            "
            @click="activeTag = activeTag === tag ? null : tag"
          >
            {{ tag }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="categories.loading" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
      <div v-for="n in 6" :key="n" class="h-64 animate-pulse rounded-xl bg-paper-2" />
    </div>
    <div v-else-if="!filtered.length" class="card flex flex-col items-center gap-3 px-6 py-12 text-center">
      <span class="text-3xl">🔍</span>
      <p class="font-medium text-ink">Ничего не найдено</p>
      <p class="max-w-xs text-sm text-ink-2">Попробуйте изменить запрос или сбросить фильтр по предмету.</p>
      <BaseButton
        variant="secondary"
        @click="
          search = '';
          activeTag = null;
        "
      >
        Сбросить фильтры
      </BaseButton>
    </div>
    <div v-else class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 items-stretch">
      <div
        v-for="category in filtered"
        :key="category.id"
        class="card flex flex-col overflow-hidden transition-transform hover:-translate-y-0.5"
      >
        <img
          v-if="category.has_image"
          :src="getCategoryImageUrl(category.id)"
          alt=""
          class="h-32 w-full object-cover"
        />
        <div v-else class="flex h-32 w-full items-center justify-center bg-moss/15 text-5xl">
          {{ subjectTheme(category.name, category.id).icon }}
        </div>

        <div class="flex flex-1 flex-col gap-3 p-5">
          <div class="flex items-start justify-between gap-2">
            <h2 class="text-lg font-semibold text-ink">{{ capitalize(category.name) }}</h2>
            <ApplicationStatusBadge :status="category.my_application_status" />
          </div>
          <p v-if="category.description" class="line-clamp-2 text-sm text-ink-2">{{ category.description }}</p>

          <div class="flex flex-wrap gap-1.5 text-xs">
            <span class="rounded-full bg-paper-2 px-2.5 py-1 font-medium text-ink-2">
              {{ lessonsLabel(category.lesson_count) }}
            </span>
            <span v-if="hoursLabel(category.total_duration_seconds)" class="rounded-full bg-paper-2 px-2.5 py-1 font-medium text-ink-2">
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
  </PageContainer>
</template>
