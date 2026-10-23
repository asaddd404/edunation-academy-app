<script setup lang="ts">
import { Trophy } from "@lucide/vue";
import { onMounted, ref } from "vue";

import ApplicationStatusBadge from "@/components/application/ApplicationStatusBadge.vue";
import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import PaginationControls from "@/components/ui/PaginationControls.vue";
import { useApplicationsStore } from "@/stores/applications";
import type { ApplicationStatus } from "@/types";
import { describeApiError } from "@/utils/apiError";

const applications = useApplicationsStore();

// Loading and failure are states of their own: before, the empty state
// ("Заявок пока нет") showed while the list was still on its way, and stayed
// when it failed -- telling a student with five applications they had none.
const loading = ref(true);
const loadError = ref("");

async function load(page = 1) {
  loading.value = true;
  loadError.value = "";
  try {
    await applications.fetchMine(page);
  } catch (e) {
    loadError.value = describeApiError(e, "Не удалось загрузить заявки.");
  } finally {
    loading.value = false;
  }
}

onMounted(() => load());

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "long", year: "numeric" });
}

const DOT_CLASS: Record<ApplicationStatus, string> = {
  pending: "bg-marigold",
  approved: "bg-moss",
  rejected: "bg-clay",
};
</script>

<template>
  <PageContainer>
    <PageHeader title="Мои заявки" />

    <div v-if="loading" class="max-w-[42rem] space-y-3">
      <div v-for="i in 3" :key="i" class="h-28 animate-pulse rounded-2xl bg-paper-2" />
    </div>

    <div v-else-if="loadError" class="card flex flex-col items-center gap-3 px-6 py-10 text-center" role="alert">
      <p class="text-red-700 dark:text-red-400">{{ loadError }}</p>
      <button type="button" class="btn-ghost" @click="load()">Повторить</button>
    </div>

    <div v-else-if="!applications.myApplications.length" class="card flex flex-col items-center gap-3 px-6 py-12 text-center">
      <div class="flex h-16 w-16 items-center justify-center rounded-full bg-moss/15 text-moss">
          <Trophy :size="30" :stroke-width="1.6" />
        </div>
      <p class="font-medium text-ink">Заявок пока нет</p>
      <p class="max-w-xs text-sm text-ink-2">Подайте заявку на предмет в каталоге, чтобы получить доступ к урокам и тестам.</p>
      <router-link to="/catalog" class="btn-primary">Перейти в каталог</router-link>
    </div>

    <ul v-else class="max-w-[42rem] space-y-0">
      <li
        v-for="(application, index) in applications.myApplications"
        :key="application.id"
        class="relative border-l-2 pb-6 pl-9 last:pb-0"
        :class="index < applications.myApplications.length - 1 ? 'border-line' : 'border-transparent'"
      >
        <span
          class="absolute -left-[7px] top-1.5 h-3.5 w-3.5 rounded-full ring-4 ring-sand"
          :class="DOT_CLASS[application.status]"
        />
        <div class="card p-4">
          <div class="flex items-start justify-between gap-2">
            <h2 class="font-semibold text-ink">{{ application.category_name ?? `Категория #${application.category_id}` }}</h2>
            <ApplicationStatusBadge :status="application.status" />
          </div>
          <p class="mt-1 text-xs text-ink-3">Подано {{ formatDate(application.created_at) }}</p>
          <p v-if="application.decided_at" class="text-xs text-ink-3">Решение принято {{ formatDate(application.decided_at) }}</p>

          <router-link
            v-if="application.status === 'approved'"
            :to="`/categories/${application.category_id}`"
            class="btn-primary mt-3 inline-flex"
          >
            Перейти к урокам →
          </router-link>
        </div>
      </li>
    </ul>

    <PaginationControls
      :page="applications.myApplicationsPage.page"
      :pages="applications.myApplicationsPage.pages"
      :total="applications.myApplicationsPage.total"
      class="mt-4"
      @change="load"
    />
  </PageContainer>
</template>
