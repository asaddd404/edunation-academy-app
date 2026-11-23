<script setup lang="ts">
import { ClipboardList, FolderKanban, Users } from "@lucide/vue";
import { ref } from "vue";

import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import AdminApplicationsView from "@/views/admin/AdminApplicationsView.vue";
import AdminCategoriesView from "@/views/admin/AdminCategoriesView.vue";
import AdminUsersView from "@/views/admin/AdminUsersView.vue";

type Tab = "users" | "categories" | "applications";

const TABS: { id: Tab; label: string; icon: typeof Users }[] = [
  { id: "users", label: "Пользователи", icon: Users },
  { id: "categories", label: "Категории", icon: FolderKanban },
  { id: "applications", label: "Заявки", icon: ClipboardList },
];

const tab = ref<Tab>("users");
</script>

<template>
  <PageContainer>
    <PageHeader title="Админ-панель" />

    <!-- Three equal columns on a phone: with flex-wrap the third tab fell
         onto a line of its own. -->
    <div class="mb-6 grid w-full grid-cols-3 gap-1 rounded-xl border border-line bg-paper p-1 sm:inline-flex sm:w-auto">
      <button
        v-for="t in TABS"
        :key="t.id"
        type="button"
        class="flex min-h-11 items-center justify-center gap-2 rounded-lg px-1 py-2.5 text-[13px] font-medium transition-colors sm:px-4 sm:text-sm"
        :class="tab === t.id ? 'bg-moss text-moss-fg' : 'text-ink-2 hover:bg-paper-2 hover:text-ink'"
        @click="tab = t.id"
      >
        <component :is="t.icon" :size="16" :stroke-width="1.8" class="hidden shrink-0 sm:block" />
        {{ t.label }}
      </button>
    </div>

    <AdminUsersView v-if="tab === 'users'" />
    <AdminCategoriesView v-else-if="tab === 'categories'" />
    <AdminApplicationsView v-else />
  </PageContainer>
</template>
