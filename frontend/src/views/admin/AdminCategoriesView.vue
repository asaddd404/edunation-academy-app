<script setup lang="ts">
import { BookOpen, Plus, X } from "@lucide/vue";
import { onMounted, reactive, ref } from "vue";

import * as adminApi from "@/api/admin";
import * as categoriesApi from "@/api/categories";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import BaseInput from "@/components/ui/BaseInput.vue";
import PaginationControls from "@/components/ui/PaginationControls.vue";
import type { CategoryAdmin, User } from "@/types";

interface PageState {
  page: number;
  total: number;
  pages: number;
}
function freshPageState(): PageState {
  return { page: 1, total: 0, pages: 0 };
}

const loading = ref(true);
const categories = ref<CategoryAdmin[]>([]);
const categoriesPage = reactive(freshPageState());

// Every teacher, not just whichever page of the Users table happens to be
// showing -- the assignment dropdown needs the whole list up front.
const allTeachers = ref<User[]>([]);

const newCategoryName = ref("");
const newCategoryDescription = ref("");
const creatingCategory = ref(false);
const assignTeacherByCategory = reactive<Record<number, string>>({});
const assigningCategoryId = ref<number | null>(null);

async function loadCategories(page = 1) {
  const res = await adminApi.listCategoriesForAdmin({ page, per_page: 60 });
  categories.value = res.items;
  categoriesPage.page = res.page;
  categoriesPage.total = res.total;
  categoriesPage.pages = res.pages;
}

async function loadAllTeachers() {
  const res = await adminApi.listUsers({ role: "teacher", per_page: 100 });
  allTeachers.value = res.items;
}

onMounted(async () => {
  loading.value = true;
  try {
    await Promise.all([loadCategories(), loadAllTeachers()]);
  } finally {
    loading.value = false;
  }
});

async function handleCreateCategory() {
  if (!newCategoryName.value.trim()) return;
  creatingCategory.value = true;
  try {
    await categoriesApi.createCategory({
      name: newCategoryName.value,
      description: newCategoryDescription.value || undefined,
    });
    newCategoryName.value = "";
    newCategoryDescription.value = "";
    await loadCategories(1);
  } finally {
    creatingCategory.value = false;
  }
}

function availableTeachers(category: CategoryAdmin) {
  const assignedIds = new Set(category.teachers.map((t) => t.id));
  return allTeachers.value.filter((t) => !assignedIds.has(t.id));
}

async function handleAssignTeacher(categoryId: number) {
  const teacherId = assignTeacherByCategory[categoryId];
  if (!teacherId) return;
  assigningCategoryId.value = categoryId;
  try {
    await categoriesApi.assignTeacher(categoryId, Number(teacherId));
    assignTeacherByCategory[categoryId] = "";
    await loadCategories(categoriesPage.page);
  } finally {
    assigningCategoryId.value = null;
  }
}

async function handleUnassignTeacher(categoryId: number, teacherId: number) {
  await categoriesApi.unassignTeacher(categoryId, teacherId);
  await loadCategories(categoriesPage.page);
}
</script>

<template>
  <div class="space-y-6">
    <!-- ── Create category ──────────────────────────────────────────── -->
    <form class="card flex w-full flex-col gap-3 p-5 sm:flex-row sm:items-end" @submit.prevent="handleCreateCategory">
      <BaseInput v-model="newCategoryName" label="Новая категория" placeholder="Например, Химия" class="flex-1" />
      <BaseInput v-model="newCategoryDescription" label="Описание" class="flex-1" />
      <BaseButton type="submit" :disabled="!newCategoryName.trim() || creatingCategory" class="flex items-center gap-1.5">
        <Plus :size="16" :stroke-width="2" />
        Создать
      </BaseButton>
    </form>

    <div v-if="loading" class="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
      <div v-for="i in 3" :key="i" class="h-48 animate-pulse rounded-xl bg-paper-2" />
    </div>

    <template v-else>
      <div v-if="categories.length" class="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
        <div v-for="category in categories" :key="category.id" class="card flex flex-col p-5">
          <div class="mb-3 flex items-center gap-3">
            <img
              v-if="category.has_image"
              :src="categoriesApi.getCategoryImageUrl(category.id)"
              alt=""
              class="h-12 w-12 shrink-0 rounded-lg object-cover"
            />
            <div v-else class="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-paper-2 text-ink-3">
              <BookOpen :size="20" :stroke-width="1.8" />
            </div>
            <div class="min-w-0">
              <p class="truncate font-medium text-ink">{{ category.name }}</p>
              <p class="text-xs text-ink-3">{{ category.lesson_count }} уроков</p>
            </div>
          </div>

          <p class="mb-4 line-clamp-2 flex-1 text-sm text-ink-2">{{ category.description || "Без описания" }}</p>

          <div class="mb-3 flex flex-wrap items-center gap-1.5">
            <span v-if="!category.teachers.length" class="text-xs text-ink-3">Учителя не назначены</span>
            <BaseBadge v-for="t in category.teachers" :key="t.id" tone="neutral">
              {{ t.first_name }} {{ t.last_name }}
              <button
                class="ml-1.5 align-middle text-ink-3 hover:text-clay"
                title="Отвязать"
                aria-label="Отвязать учителя"
                @click="handleUnassignTeacher(category.id, t.id)"
              >
                <X :size="12" :stroke-width="2" class="inline" />
              </button>
            </BaseBadge>
          </div>

          <div class="flex items-center gap-2">
            <select v-model="assignTeacherByCategory[category.id]" class="input min-h-11 min-w-0 flex-1 px-2 py-2 text-sm">
              <option value="">Назначить учителя…</option>
              <option v-for="teacher in availableTeachers(category)" :key="teacher.id" :value="teacher.id">
                {{ teacher.first_name }} {{ teacher.last_name }}
              </option>
            </select>
            <BaseButton
              variant="secondary"
              :disabled="!assignTeacherByCategory[category.id] || assigningCategoryId === category.id"
              @click="handleAssignTeacher(category.id)"
            >
              Назначить
            </BaseButton>
          </div>
        </div>
      </div>

      <div v-else class="card flex flex-col items-center gap-2 px-6 py-12 text-center">
        <BookOpen :size="28" :stroke-width="1.5" class="text-ink-3" />
        <p class="font-medium text-ink">Пока нет ни одной категории</p>
        <p class="max-w-xs text-sm text-ink-2">Создайте первую категорию формой выше, чтобы учителя могли наполнять её уроками.</p>
      </div>

      <PaginationControls
        :page="categoriesPage.page"
        :pages="categoriesPage.pages"
        :total="categoriesPage.total"
        @change="loadCategories"
      />
    </template>
  </div>
</template>
