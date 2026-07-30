<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";

import * as adminApi from "@/api/admin";
import * as applicationsApi from "@/api/applications";
import * as categoriesApi from "@/api/categories";
import ApplicationStatusBadge from "@/components/application/ApplicationStatusBadge.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import BaseInput from "@/components/ui/BaseInput.vue";
import PaginationControls from "@/components/ui/PaginationControls.vue";
import type { Application, CategoryAdmin, Role, User } from "@/types";

type Tab = "users" | "categories" | "applications";

const tab = ref<Tab>("users");

interface PageState {
  page: number;
  total: number;
  pages: number;
}

function freshPageState(): PageState {
  return { page: 1, total: 0, pages: 0 };
}

const users = ref<User[]>([]);
const usersPage = reactive(freshPageState());

const categories = ref<CategoryAdmin[]>([]);
const categoriesPage = reactive(freshPageState());

const applications = ref<Application[]>([]);
const applicationsPage = reactive(freshPageState());

// Assigning a teacher to a category needs every teacher, not just whichever
// page of /admin/users happens to be showing -- fetched once, separately
// from the paginated "Пользователи" table below.
const allTeachers = ref<User[]>([]);

const newCategoryName = ref("");
const newCategoryDescription = ref("");
const assignTeacherByCategory = reactive<Record<number, string>>({});
const assigningCategoryId = ref<number | null>(null);
const decidingApplicationId = ref<number | null>(null);

async function loadUsers(page = 1) {
  const res = await adminApi.listUsers({ page });
  users.value = res.items;
  usersPage.page = res.page;
  usersPage.total = res.total;
  usersPage.pages = res.pages;
}

async function loadAllTeachers() {
  const res = await adminApi.listUsers({ role: "teacher", per_page: 100 });
  allTeachers.value = res.items;
}

async function loadCategories(page = 1) {
  const res = await adminApi.listCategoriesForAdmin({ page });
  categories.value = res.items;
  categoriesPage.page = res.page;
  categoriesPage.total = res.total;
  categoriesPage.pages = res.pages;
}

async function loadApplications(page = 1) {
  const res = await applicationsApi.listAllApplications({ page });
  applications.value = res.items;
  applicationsPage.page = res.page;
  applicationsPage.total = res.total;
  applicationsPage.pages = res.pages;
}

onMounted(async () => {
  await Promise.all([loadUsers(), loadAllTeachers(), loadCategories(), loadApplications()]);
});

async function handleRoleChange(user: User, role: Role) {
  await adminApi.updateUser(user.id, { role });
  await Promise.all([loadUsers(usersPage.page), loadAllTeachers()]);
}

async function handleActiveToggle(user: User) {
  await adminApi.updateUser(user.id, { is_active: !user.is_active });
  await loadUsers(usersPage.page);
}

async function handleCreateCategory() {
  if (!newCategoryName.value.trim()) return;
  await categoriesApi.createCategory({
    name: newCategoryName.value,
    description: newCategoryDescription.value || undefined,
  });
  newCategoryName.value = "";
  newCategoryDescription.value = "";
  await loadCategories(1);
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

async function handleDecideApplication(applicationId: number, decision: "approve" | "reject") {
  decidingApplicationId.value = applicationId;
  try {
    if (decision === "approve") await applicationsApi.approveApplication(applicationId);
    else await applicationsApi.rejectApplication(applicationId);
    await loadApplications(applicationsPage.page);
  } finally {
    decidingApplicationId.value = null;
  }
}
</script>

<template>
  <div>
    <h1 class="mb-6 text-2xl font-semibold">Админ-панель</h1>

    <div class="mb-6 flex gap-2 border-b border-fg/10 pb-2">
      <button
        v-for="t in (['users', 'categories', 'applications'] as Tab[])"
        :key="t"
        class="rounded-lg px-3 py-2 text-sm"
        :class="tab === t ? 'bg-accent text-bg' : 'text-fg/60 hover:bg-fg/5'"
        @click="tab = t"
      >
        {{ t === "users" ? "Пользователи" : t === "categories" ? "Категории" : "Заявки" }}
      </button>
    </div>

    <section v-if="tab === 'users'" class="space-y-3">
      <div
        v-for="user in users"
        :key="user.id"
        class="flex flex-col gap-2 rounded-xl border border-fg/10 p-4 sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <p class="font-medium">{{ user.first_name }} {{ user.last_name }}</p>
          <p class="text-sm text-fg/60">{{ user.phone }}</p>
        </div>
        <div class="flex items-center gap-2">
          <select
            class="rounded-lg border border-fg/20 bg-transparent px-2 py-2 text-sm"
            :value="user.role"
            @change="handleRoleChange(user, ($event.target as HTMLSelectElement).value as Role)"
          >
            <option value="student">student</option>
            <option value="teacher">teacher</option>
            <option value="admin">admin</option>
          </select>
          <BaseButton variant="secondary" @click="handleActiveToggle(user)">
            {{ user.is_active ? "Деактивировать" : "Активировать" }}
          </BaseButton>
        </div>
      </div>

      <PaginationControls
        :page="usersPage.page"
        :pages="usersPage.pages"
        :total="usersPage.total"
        @change="loadUsers"
      />
    </section>

    <section v-else-if="tab === 'categories'" class="space-y-6">
      <form class="flex flex-col gap-3 rounded-xl border border-fg/10 p-4 sm:flex-row sm:items-end" @submit.prevent="handleCreateCategory">
        <BaseInput v-model="newCategoryName" label="Новая категория" placeholder="Например, Химия" class="flex-1" />
        <BaseInput v-model="newCategoryDescription" label="Описание" class="flex-1" />
        <BaseButton type="submit">Создать</BaseButton>
      </form>

      <div v-for="category in categories" :key="category.id" class="flex gap-4 rounded-xl border border-fg/10 p-4">
        <img
          v-if="category.has_image"
          :src="categoriesApi.getCategoryImageUrl(category.id)"
          alt=""
          class="h-16 w-16 shrink-0 rounded-lg object-cover"
        />
        <div class="flex-1">
        <p class="font-medium">{{ category.name }}</p>
        <p class="mb-3 text-sm text-fg/60">{{ category.description }}</p>

        <div class="mb-3 flex flex-wrap items-center gap-2">
          <span v-if="!category.teachers.length" class="text-sm text-fg/50">Учителя не назначены</span>
          <BaseBadge v-for="t in category.teachers" :key="t.id" tone="neutral">
            {{ t.first_name }} {{ t.last_name }}
            <button
              class="ml-1.5 text-fg/40 hover:text-red-500"
              title="Отвязать"
              @click="handleUnassignTeacher(category.id, t.id)"
            >
              ×
            </button>
          </BaseBadge>
        </div>

        <div class="flex items-center gap-2">
          <select
            v-model="assignTeacherByCategory[category.id]"
            class="rounded-lg border border-fg/20 bg-transparent px-2 py-2 text-sm"
          >
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

      <PaginationControls
        :page="categoriesPage.page"
        :pages="categoriesPage.pages"
        :total="categoriesPage.total"
        @change="loadCategories"
      />
    </section>

    <section v-else class="space-y-3">
      <div
        v-for="application in applications"
        :key="application.id"
        class="flex flex-col gap-3 rounded-xl border border-fg/10 p-4 sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <p class="font-medium">{{ application.student_name }}</p>
          <p class="text-sm text-fg/60">{{ application.category_name }}</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <template v-if="application.status === 'pending'">
            <BaseButton
              variant="secondary"
              :disabled="decidingApplicationId === application.id"
              @click="handleDecideApplication(application.id, 'reject')"
            >
              Отклонить
            </BaseButton>
            <BaseButton
              :disabled="decidingApplicationId === application.id"
              @click="handleDecideApplication(application.id, 'approve')"
            >
              Одобрить
            </BaseButton>
          </template>
          <ApplicationStatusBadge :status="application.status" />
        </div>
      </div>

      <PaginationControls
        :page="applicationsPage.page"
        :pages="applicationsPage.pages"
        :total="applicationsPage.total"
        @change="loadApplications"
      />
    </section>
  </div>
</template>
