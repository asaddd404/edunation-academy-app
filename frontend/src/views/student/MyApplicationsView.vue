<script setup lang="ts">
import { onMounted } from "vue";

import ApplicationStatusBadge from "@/components/application/ApplicationStatusBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import { useApplicationsStore } from "@/stores/applications";
import type { ApplicationStatus } from "@/types";

const applications = useApplicationsStore();

onMounted(() => applications.fetchMine());

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "long", year: "numeric" });
}

const DOT_CLASS: Record<ApplicationStatus, string> = {
  pending: "bg-amber-500",
  approved: "bg-emerald-500",
  rejected: "bg-red-500",
};
</script>

<template>
  <div class="mx-auto max-w-2xl">
    <h1 class="mb-6 text-2xl font-semibold">
      <span class="text-gradient-brand">Мои заявки</span>
    </h1>

    <div v-if="!applications.myApplications.length" class="glass-card flex flex-col items-center gap-3 px-6 py-12 text-center">
      <div class="flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-3xl shadow-lg shadow-indigo-500/20">
        🏆
      </div>
      <p class="font-medium">Заявок пока нет</p>
      <p class="max-w-xs text-sm text-fg/60">Подайте заявку на предмет в каталоге, чтобы получить доступ к урокам и тестам.</p>
      <router-link to="/catalog">
        <BaseButton variant="cta">Перейти в каталог</BaseButton>
      </router-link>
    </div>

    <ul v-else class="space-y-0">
      <li
        v-for="(application, index) in applications.myApplications"
        :key="application.id"
        class="relative pb-6 pl-9 last:pb-0"
        :class="{ 'border-l-2 border-border': index < applications.myApplications.length - 1 }"
      >
        <span
          class="absolute -left-[7px] top-1.5 h-3.5 w-3.5 rounded-full ring-4 ring-bg"
          :class="DOT_CLASS[application.status]"
        />
        <div class="glass-card p-4">
          <div class="flex items-start justify-between gap-2">
            <h2 class="font-semibold">{{ application.category_name ?? `Категория #${application.category_id}` }}</h2>
            <ApplicationStatusBadge :status="application.status" />
          </div>
          <p class="mt-1 text-xs text-fg/50">Подано {{ formatDate(application.created_at) }}</p>
          <p v-if="application.decided_at" class="text-xs text-fg/50">Решение принято {{ formatDate(application.decided_at) }}</p>

          <router-link v-if="application.status === 'approved'" :to="`/categories/${application.category_id}`" class="mt-3 inline-block">
            <BaseButton variant="cta">Перейти к урокам →</BaseButton>
          </router-link>
        </div>
      </li>
    </ul>
  </div>
</template>
