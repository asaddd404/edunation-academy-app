<script setup lang="ts">
import { Ban, Copy, KeyRound, Search, UserCheck, X } from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";

import * as adminApi from "@/api/admin";
import BaseButton from "@/components/ui/BaseButton.vue";
import PaginationControls from "@/components/ui/PaginationControls.vue";
import { useModalFocusTrap } from "@/composables/useModalFocusTrap";
import type { Role, User } from "@/types";

interface PageState {
  page: number;
  total: number;
  pages: number;
}
function freshPageState(): PageState {
  return { page: 1, total: 0, pages: 0 };
}

const ROLES: Role[] = ["student", "teacher", "admin"];
const ROLE_LABEL: Record<Role, string> = { student: "Ученики", teacher: "Учителя", admin: "Админы" };

const loading = ref(true);
const users = ref<User[]>([]);
const usersPage = reactive(freshPageState());

// Server-side: accurate across every page, not just whatever's loaded.
const roleFilter = ref<Role | "all">("all");
// Client-side over the current page: the backend has no `is_active` or
// text-search filter, so these narrow what's already loaded rather than
// querying the whole table. A large `per_page` below keeps that narrowing
// meaningful for a school-sized user list.
const statusFilter = ref<"all" | "active" | "blocked">("all");
const searchQuery = ref("");

// One lightweight per_page=1 request per role, fired once, so the tab
// labels show real totals instead of "however many are on this page".
const roleCounts = reactive<Record<Role | "all", number>>({ all: 0, student: 0, teacher: 0, admin: 0 });

async function loadRoleCounts() {
  const [all, student, teacher, admin] = await Promise.all([
    adminApi.listUsers({ per_page: 1 }),
    adminApi.listUsers({ per_page: 1, role: "student" }),
    adminApi.listUsers({ per_page: 1, role: "teacher" }),
    adminApi.listUsers({ per_page: 1, role: "admin" }),
  ]);
  roleCounts.all = all.total;
  roleCounts.student = student.total;
  roleCounts.teacher = teacher.total;
  roleCounts.admin = admin.total;
}

async function loadUsers(page = 1) {
  const res = await adminApi.listUsers({
    page,
    per_page: 100,
    role: roleFilter.value === "all" ? undefined : roleFilter.value,
  });
  users.value = res.items;
  usersPage.page = res.page;
  usersPage.total = res.total;
  usersPage.pages = res.pages;
}

async function setRoleFilter(role: Role | "all") {
  if (roleFilter.value === role) return;
  roleFilter.value = role;
  loading.value = true;
  try {
    await loadUsers(1);
  } finally {
    loading.value = false;
  }
}

const filteredUsers = computed(() => {
  let list = users.value;
  if (statusFilter.value !== "all") {
    list = list.filter((u) => (statusFilter.value === "active" ? u.is_active : !u.is_active));
  }
  const q = searchQuery.value.trim().toLowerCase();
  if (q) {
    list = list.filter(
      (u) => `${u.first_name} ${u.last_name}`.toLowerCase().includes(q) || u.phone.toLowerCase().includes(q),
    );
  }
  return list;
});

onMounted(async () => {
  loading.value = true;
  try {
    await Promise.all([loadUsers(), loadRoleCounts()]);
  } finally {
    loading.value = false;
  }
});

const updatingUserId = ref<number | null>(null);

async function handleRoleChange(user: User, role: Role) {
  updatingUserId.value = user.id;
  try {
    await adminApi.updateUser(user.id, { role });
    await Promise.all([loadUsers(usersPage.page), loadRoleCounts()]);
  } finally {
    updatingUserId.value = null;
  }
}

async function handleActiveToggle(user: User) {
  updatingUserId.value = user.id;
  try {
    await adminApi.updateUser(user.id, { is_active: !user.is_active });
    await loadUsers(usersPage.page);
  } finally {
    updatingUserId.value = null;
  }
}

// ── Password reset: a one-time reveal -- the temporary password only ever
// exists in this component's state, never persisted, so closing the dialog
// is the only "copy" the admin gets. ──────────────────────────────────────
const resetModalUser = ref<User | null>(null);
const resetModalRef = ref<HTMLElement | null>(null);
const resettingPassword = ref(false);
const temporaryPassword = ref("");
const copyState = ref<"idle" | "copied">("idle");

function closeResetModal() {
  if (resettingPassword.value) return;
  resetModalUser.value = null;
  temporaryPassword.value = "";
  copyState.value = "idle";
}
useModalFocusTrap(resetModalRef, closeResetModal);

async function handleResetPassword(user: User) {
  resetModalUser.value = user;
  temporaryPassword.value = "";
  copyState.value = "idle";
  resettingPassword.value = true;
  try {
    const res = await adminApi.resetUserPassword(user.id);
    temporaryPassword.value = res.temporary_password;
  } catch {
    resetModalUser.value = null;
  } finally {
    resettingPassword.value = false;
  }
}

async function copyPassword() {
  await navigator.clipboard.writeText(temporaryPassword.value);
  copyState.value = "copied";
  setTimeout(() => (copyState.value = "idle"), 2000);
}
</script>

<template>
  <div class="space-y-4">
    <!-- ── Controls ─────────────────────────────────────────────────── -->
    <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      <div class="relative w-full max-w-md">
        <Search :size="16" :stroke-width="1.8" class="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Поиск по имени или номеру телефона..."
          class="input py-2.5 pl-9 pr-3 text-sm"
        />
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <div class="inline-flex overflow-hidden rounded-lg border border-line">
          <button
            type="button"
            class="min-h-11 px-3 py-2 text-xs font-medium transition-colors"
            :class="roleFilter === 'all' ? 'bg-moss text-moss-fg' : 'text-ink-2 hover:bg-paper-2 hover:text-ink'"
            @click="setRoleFilter('all')"
          >
            Все ({{ roleCounts.all }})
          </button>
          <button
            v-for="role in ROLES"
            :key="role"
            type="button"
            class="min-h-11 border-l border-line px-3 py-2 text-xs font-medium transition-colors"
            :class="roleFilter === role ? 'bg-moss text-moss-fg' : 'text-ink-2 hover:bg-paper-2 hover:text-ink'"
            @click="setRoleFilter(role)"
          >
            {{ ROLE_LABEL[role] }} ({{ roleCounts[role] }})
          </button>
        </div>

        <select v-model="statusFilter" class="input min-h-11 w-auto px-3 py-2 text-xs">
          <option value="all">Все статусы</option>
          <option value="active">Только активные</option>
          <option value="blocked">Заблокированные</option>
        </select>
      </div>
    </div>

    <div v-if="loading" class="space-y-2">
      <div v-for="i in 6" :key="i" class="h-16 animate-pulse rounded-xl bg-paper-2" />
    </div>

    <template v-else>
      <!-- ── Mobile: cards ──────────────────────────────────────────── -->
      <ul v-if="filteredUsers.length" class="divide-y divide-line rounded-xl border border-line sm:hidden">
        <li v-for="user in filteredUsers" :key="user.id" class="flex flex-col gap-3 p-4">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="font-medium text-ink">{{ user.first_name }} {{ user.last_name }}</p>
              <p class="text-xs text-ink-3">{{ user.phone }}</p>
            </div>
            <span
              class="badge shrink-0 border"
              :class="user.is_active ? 'border-moss/20 bg-moss/10 text-moss' : 'border-clay/20 bg-clay/10 text-clay'"
            >
              {{ user.is_active ? "Активен" : "Заблокирован" }}
            </span>
          </div>

          <select
            :value="user.role"
            :disabled="updatingUserId === user.id"
            class="input min-h-11 w-full px-2 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
            @change="handleRoleChange(user, ($event.target as HTMLSelectElement).value as Role)"
          >
            <option value="student">Ученик</option>
            <option value="teacher">Учитель</option>
            <option value="admin">Админ</option>
          </select>

          <div class="flex gap-2">
            <button
              type="button"
              class="flex min-h-11 flex-1 items-center justify-center gap-1.5 rounded-lg border border-line p-2 text-sm text-ink-2 transition-colors hover:bg-paper-2 hover:text-ink"
              aria-label="Сбросить пароль"
              @click="handleResetPassword(user)"
            >
              <KeyRound :size="15" :stroke-width="1.8" />
              Сбросить пароль
            </button>
            <button
              type="button"
              class="flex min-h-11 flex-1 items-center justify-center gap-1.5 rounded-lg border border-line p-2 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50"
              :class="user.is_active ? 'text-ink-2 hover:bg-clay/10 hover:text-clay' : 'text-ink-2 hover:bg-moss/10 hover:text-moss'"
              :disabled="updatingUserId === user.id"
              :aria-label="user.is_active ? 'Заблокировать' : 'Активировать'"
              @click="handleActiveToggle(user)"
            >
              <Ban v-if="user.is_active" :size="15" :stroke-width="1.8" />
              <UserCheck v-else :size="15" :stroke-width="1.8" />
              {{ user.is_active ? "Заблокировать" : "Активировать" }}
            </button>
          </div>
        </li>
      </ul>
      <p v-else class="rounded-xl border border-line py-10 text-center text-sm text-ink-3 sm:hidden">Ничего не найдено.</p>

      <!-- ── Desktop: table ─────────────────────────────────────────── -->
      <div class="hidden overflow-x-auto rounded-xl border border-line sm:block">
        <table class="w-full min-w-[720px] text-left text-sm">
          <thead>
            <tr class="border-b border-line bg-paper-2 text-xs uppercase tracking-wide text-ink-3">
              <th class="px-4 py-3 font-medium">Пользователь</th>
              <th class="px-4 py-3 font-medium">Роль</th>
              <th class="px-4 py-3 font-medium">Статус</th>
              <th class="px-4 py-3 text-right font-medium">Действия</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-line">
            <tr v-for="user in filteredUsers" :key="user.id" class="transition-colors hover:bg-paper-2">
              <td class="px-4 py-3">
                <p class="font-medium text-ink">{{ user.first_name }} {{ user.last_name }}</p>
                <p class="text-xs text-ink-3">{{ user.phone }}</p>
              </td>
              <td class="px-4 py-3">
                <select
                  :value="user.role"
                  :disabled="updatingUserId === user.id"
                  class="input px-2 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
                  @change="handleRoleChange(user, ($event.target as HTMLSelectElement).value as Role)"
                >
                  <option value="student">Ученик</option>
                  <option value="teacher">Учитель</option>
                  <option value="admin">Админ</option>
                </select>
              </td>
              <td class="px-4 py-3">
                <span
                  class="badge border"
                  :class="user.is_active ? 'border-moss/20 bg-moss/10 text-moss' : 'border-clay/20 bg-clay/10 text-clay'"
                >
                  {{ user.is_active ? "Активен" : "Заблокирован" }}
                </span>
              </td>
              <td class="px-4 py-3">
                <div class="flex justify-end gap-1.5">
                  <button
                    type="button"
                    class="rounded-lg p-2 text-ink-2 transition-colors hover:bg-paper-2 hover:text-ink"
                    aria-label="Сбросить пароль"
                    title="Сбросить пароль"
                    @click="handleResetPassword(user)"
                  >
                    <KeyRound :size="15" :stroke-width="1.8" />
                  </button>
                  <button
                    type="button"
                    class="rounded-lg p-2 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                    :class="user.is_active ? 'text-ink-2 hover:bg-clay/10 hover:text-clay' : 'text-ink-2 hover:bg-moss/10 hover:text-moss'"
                    :disabled="updatingUserId === user.id"
                    :aria-label="user.is_active ? 'Заблокировать' : 'Активировать'"
                    :title="user.is_active ? 'Заблокировать' : 'Активировать'"
                    @click="handleActiveToggle(user)"
                  >
                    <Ban v-if="user.is_active" :size="15" :stroke-width="1.8" />
                    <UserCheck v-else :size="15" :stroke-width="1.8" />
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!filteredUsers.length">
              <td colspan="4" class="px-4 py-10 text-center text-sm text-ink-3">Ничего не найдено.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <PaginationControls
        :page="usersPage.page"
        :pages="usersPage.pages"
        :total="usersPage.total"
        @change="loadUsers"
      />
    </template>

    <!-- ── Reset-password dialog ──────────────────────────────────────── -->
    <div v-if="resetModalUser" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" @click.self="closeResetModal">
      <div ref="resetModalRef" role="dialog" aria-modal="true" class="card w-full max-w-sm p-5">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="font-display text-base font-semibold text-ink">Сброс пароля</h2>
          <button
            class="flex h-11 w-11 items-center justify-center rounded-lg text-ink-2 transition-colors hover:bg-paper-2 hover:text-ink"
            aria-label="Закрыть"
            @click="closeResetModal"
          >
            <X :size="16" :stroke-width="1.8" />
          </button>
        </div>
        <p class="mb-3 text-sm text-ink-2">{{ resetModalUser.first_name }} {{ resetModalUser.last_name }} · {{ resetModalUser.phone }}</p>

        <div v-if="resettingPassword" class="py-4 text-center text-sm text-ink-2">Генерируем пароль…</div>
        <template v-else-if="temporaryPassword">
          <p class="mb-2 text-xs text-ink-3">
            Новый временный пароль показывается один раз — передайте его пользователю сейчас.
          </p>
          <div class="flex items-center gap-2">
            <code class="flex-1 rounded-lg border border-line-strong bg-sand px-3 py-2 font-mono text-sm text-moss">
              {{ temporaryPassword }}
            </code>
            <button
              type="button"
              class="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-line-strong text-ink-2 transition-colors hover:bg-paper-2"
              :aria-label="copyState === 'copied' ? 'Скопировано' : 'Скопировать'"
              :title="copyState === 'copied' ? 'Скопировано' : 'Скопировать'"
              @click="copyPassword"
            >
              <Copy :size="15" :stroke-width="1.8" />
            </button>
          </div>
        </template>

        <div class="mt-4 flex justify-end">
          <BaseButton variant="secondary" @click="closeResetModal">Готово</BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>
