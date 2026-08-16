<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { listSections } from "@/api/sections";
import PageContainer from "@/components/layout/PageContainer.vue";
import CatalogMobileNav from "@/components/catalog/CatalogMobileNav.vue";
import MillerColumn from "@/components/catalog/MillerColumn.vue";
import type { MillerItem } from "@/components/catalog/MillerColumn.vue";
import { useMediaQuery } from "@/composables/useMediaQuery";
import ApplicationStatusBadge from "@/components/application/ApplicationStatusBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import { useApplicationsStore } from "@/stores/applications";
import { useCategoriesStore } from "@/stores/categories";
import type { Section } from "@/types";
import { capitalize } from "@/utils/subjectTheme";

const route = useRoute();
const router = useRouter();
const categories = useCategoriesStore();
const applications = useApplicationsStore();

const search = ref(typeof route.query.q === "string" ? route.query.q : "");
const applyingId = ref<number | null>(null);

const sections = ref<Section[]>([]);
const sectionsLoading = ref(false);
const sectionsCategoryId = ref<number | null>(null);

const selectedCategoryId = computed(() => {
  const raw = route.query.category;
  const id = Number(raw);
  return typeof raw === "string" && !Number.isNaN(id) ? id : null;
});
const selectedSectionId = computed(() => {
  const raw = route.query.section;
  const id = Number(raw);
  return typeof raw === "string" && !Number.isNaN(id) ? id : null;
});

const selectedCategory = computed(
  () => categories.list.find((c) => c.id === selectedCategoryId.value) ?? null,
);
const selectedSection = computed(
  () => sections.value.find((s) => s.id === selectedSectionId.value) ?? null,
);

categories.fetchAll();

async function loadSections(categoryId: number) {
  sectionsLoading.value = true;
  sectionsCategoryId.value = categoryId;
  try {
    sections.value = await listSections(categoryId);
  } finally {
    sectionsLoading.value = false;
  }
}

watch(
  selectedCategory,
  (category) => {
    if (category && category.my_application_status === "approved") {
      loadSections(category.id);
    } else {
      sections.value = [];
      sectionsCategoryId.value = null;
    }
  },
  { immediate: true },
);

const filteredCategories = computed(() => {
  const query = search.value.trim().toLowerCase();
  if (!query) return categories.list;
  return categories.list.filter(
    (c) => c.name.toLowerCase().includes(query) || (c.description ?? "").toLowerCase().includes(query),
  );
});

const categoryItems = computed<MillerItem[]>(() =>
  filteredCategories.value.map((c) => ({
    id: c.id,
    label: capitalize(c.name),
    kind: "folder",
    meta:
      c.my_application_status === "approved"
        ? `${c.lesson_count} ур.`
        : c.my_application_status === "pending"
          ? "заявка отправлена"
          : undefined,
  })),
);

const sectionItems = computed<MillerItem[]>(() =>
  sections.value.map((s) => ({
    id: s.id,
    label: s.title,
    kind: "folder",
    meta: `${s.lessons.length} ур.`,
  })),
);

const TEST_ITEM_PREFIX = "test-";

const lessonItems = computed<MillerItem[]>(() => {
  const section = selectedSection.value;
  if (!section) return [];
  const items: MillerItem[] = section.lessons.map((lesson) => ({
    id: lesson.id,
    label: lesson.title,
    kind: "leaf",
    locked: !lesson.is_unlocked,
    done: lesson.is_passed,
  }));
  if (section.has_test) {
    items.push({
      id: `${TEST_ITEM_PREFIX}${section.id}`,
      label: "Тест раздела",
      kind: "leaf",
      locked: !section.is_test_unlocked,
      done: section.is_test_passed,
    });
  }
  return items;
});

function setQuery(next: Record<string, string | undefined>) {
  const query = { ...route.query, ...next };
  Object.keys(query).forEach((key) => {
    if (query[key] === undefined) delete query[key];
  });
  router.push({ path: "/catalog", query });
}

function selectCategory(id: number | string) {
  setQuery({ category: String(id), section: undefined });
}

function selectSection(id: number | string) {
  setQuery({ section: String(id) });
}

function selectLesson(id: number | string) {
  const raw = String(id);
  if (raw.startsWith(TEST_ITEM_PREFIX)) {
    const sectionId = raw.slice(TEST_ITEM_PREFIX.length);
    router.push(`/sections/${sectionId}/test`);
  } else {
    router.push(`/lessons/${raw}`);
  }
}

const isDesktop = useMediaQuery("(min-width: 768px)");

/** Levels the phone view drills through. Built from the same computed item
 * lists the desktop columns use, so the two never show different content. */
const mobileLevels = computed(() => {
  const levels: { title: string; items: MillerItem[]; loading?: boolean; emptyText?: string }[] = [
    {
      title: "Предметы",
      items: categoryItems.value,
      loading: categories.loading,
      emptyText: "Ничего не найдено",
    },
  ];
  // A category the student has no approved application for has nothing to
  // drill into -- the apply card is rendered instead of a third level.
  if (selectedCategory.value?.my_application_status === "approved") {
    levels.push({
      title: capitalize(selectedCategory.value.name),
      items: sectionItems.value,
      loading: sectionsLoading.value,
      emptyText: "Разделы пока не добавлены",
    });
  }
  if (selectedSection.value) {
    levels.push({
      title: selectedSection.value.title,
      items: lessonItems.value,
      emptyText: "Уроки пока не добавлены",
    });
  }
  return levels;
});

const mobileCrumbs = computed(() => {
  const crumbs: string[] = [];
  if (selectedCategory.value) crumbs.push(capitalize(selectedCategory.value.name));
  if (selectedSection.value) crumbs.push(selectedSection.value.title);
  return crumbs;
});

function handleMobileSelect(id: number | string) {
  const depth = mobileLevels.value.length;
  if (depth === 1) selectCategory(id);
  else if (depth === 2) selectSection(id);
  else selectLesson(id);
}

function goBack() {
  if (selectedSectionId.value !== null) setQuery({ section: undefined });
  else if (selectedCategoryId.value !== null) setQuery({ category: undefined, section: undefined });
}

// A search typed at one level would otherwise silently hide items at the
// next one the student drills into.
watch([selectedCategoryId, selectedSectionId], () => {
  if (!isDesktop.value) search.value = "";
});

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
  <PageContainer>
    <!-- Phone: one level at a time. The apply card still renders below when
         the chosen category has no approved application. -->
    <template v-if="!isDesktop">
      <CatalogMobileNav
        :levels="mobileLevels"
        :crumbs="mobileCrumbs"
        :search="search"
        @select="handleMobileSelect"
        @back="goBack"
        @update:search="search = $event"
      />

      <div
        v-if="selectedCategory && selectedCategory.my_application_status !== 'approved'"
        class="card mt-4 flex flex-col items-start gap-3 p-4"
      >
        <ApplicationStatusBadge :status="selectedCategory.my_application_status" />
        <p class="text-sm text-ink-2">
          {{
            selectedCategory.my_application_status === "pending"
              ? "Заявка на рассмотрении у преподавателя."
              : "Подайте заявку, чтобы открыть разделы и уроки этого предмета."
          }}
        </p>
        <BaseButton
          v-if="selectedCategory.my_application_status !== 'pending'"
          variant="cta"
          class="min-h-12 w-full"
          :disabled="applyingId === selectedCategory.id"
          @click="handleApply(selectedCategory.id)"
        >
          Подать заявку
        </BaseButton>
      </div>
    </template>

    <template v-else>
      <div class="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 class="font-display text-display-lg text-ink">Каталог предметов</h1>
          <p class="mt-1 text-sm text-ink-2">Выбирай предмет → раздел → урок.</p>
        </div>
        <input v-model="search" type="search" placeholder="Найти предмет…" class="input w-full sm:w-64" />
      </div>

      <div class="flex w-full items-start gap-6 overflow-x-auto scroll-smooth pb-6">
      <MillerColumn
        title="Предметы"
        :items="categoryItems"
        :selected-id="selectedCategoryId"
        :loading="categories.loading"
        empty-text="Ничего не найдено"
        @select="selectCategory"
      />

      <div v-if="selectedCategory && selectedCategory.my_application_status !== 'approved'" class="miller-column">
        <h2 class="miller-column-title">{{ capitalize(selectedCategory.name) }}</h2>
        <div class="miller-column-card flex flex-col items-start gap-3 p-4">
          <ApplicationStatusBadge :status="selectedCategory.my_application_status" />
          <p class="text-sm text-ink-2">
            {{
              selectedCategory.my_application_status === "pending"
                ? "Заявка на рассмотрении у преподавателя."
                : "Подайте заявку, чтобы открыть разделы и уроки этого предмета."
            }}
          </p>
          <BaseButton
            v-if="selectedCategory.my_application_status !== 'pending'"
            variant="cta"
            :disabled="applyingId === selectedCategory.id"
            @click="handleApply(selectedCategory.id)"
          >
            Подать заявку
          </BaseButton>
        </div>
      </div>

      <MillerColumn
        v-if="selectedCategory && selectedCategory.my_application_status === 'approved'"
        title="Разделы"
        :items="sectionItems"
        :selected-id="selectedSectionId"
        :loading="sectionsLoading"
        empty-text="Разделы пока не добавлены"
        @select="selectSection"
      />

        <MillerColumn
          v-if="selectedSection"
          title="Уроки"
          :items="lessonItems"
          empty-text="Уроки пока не добавлены"
          @select="selectLesson"
        />
      </div>
    </template>
  </PageContainer>
</template>
