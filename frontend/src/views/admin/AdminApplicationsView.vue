<script setup lang="ts">
import { Calendar, Check, Phone, Search, X } from "@lucide/vue";
import { computed, onMounted, reactive, ref } from "vue";

import * as applicationsApi from "@/api/applications";
import PaginationControls from "@/components/ui/PaginationControls.vue";
import type { Application, ApplicationStatus } from "@/types";

interface PageState {
  page: number;
  total: number;
  pages: number;
}
function freshPageState(): PageState {
  return { page: 1, total: 0, pages: 0 };
}

type StatusFilter = "all" | ApplicationStatus;

const STATUSES: ApplicationStatus[] = ["pending", "approved", "rejected"];
const STATUS_LABEL: Record<ApplicationStatus, string> = {
  pending: "Новые",
  approved: "Одобренные",
  rejected: "Отклонённые",
};
const STATUS_DOT: Record<ApplicationStatus, string> = {
  pending: "bg-marigold",
  approved: "bg-moss",
  rejected: "bg-clay",
};
const STATUS_BADGE_CLASS: Record<ApplicationStatus, string> = {
  pending: "border-marigold/25 bg-marigold/10 text-ink",
  approved: "border-moss/20 bg-moss/10 text-moss",
  rejected: "border-clay/20 bg-clay/10 text-clay",
};

const loading = ref(true);
const applications = ref<Application[]>([]);
const applicationsPage = reactive(freshPageState());

const statusFilter = ref<StatusFilter>("all");
const searchQuery = ref("");
const decidingApplicationId = ref<number | null>(null);

// Server-side counts, one per_page=1 request per status -- accurate across
// every page, unlike counting whatever happens to be loaded.
const statusCounts = reactive<Record<StatusFilter, number>>({ all: 0, pending: 0, approved: 0, rejected: 0 });

async function loadStatusCounts() {
  const [all, pending, approved, rejected] = await Promise.all([
    applicationsApi.listAllApplications({ per_page: 1 }),
    applicationsApi.listAllApplications({ per_page: 1, status: "pending" }),
    applicationsApi.listAllApplications({ per_page: 1, status: "approved" }),
    applicationsApi.listAllApplications({ per_page: 1, status: "rejected" }),
  ]);
  statusCounts.all = all.total;
  statusCounts.pending = pending.total;
  statusCounts.approved = approved.total;
  statusCounts.rejected = rejected.total;
}

async function loadApplications(page = 1) {
  const res = await applicationsApi.listAllApplications({
    page,
    per_page: 50,
    status: statusFilter.value === "all" ? undefined : statusFilter.value,
  });
  applications.value = res.items;
  applicationsPage.page = res.page;
  applicationsPage.total = res.total;
  applicationsPage.pages = res.pages;
}

async function setStatusFilter(status: StatusFilter) {
  if (statusFilter.value === status) return;
  statusFilter.value = status;
  loading.value = true;
  try {
    await loadApplications(1);
  } finally {
    loading.value = false;
  }
}

const filteredApplications = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return applications.value;
  return applications.value.filter(
    (a) =>
      (a.student_name ?? "").toLowerCase().includes(q) ||
      (a.student_phone ?? "").toLowerCase().includes(q) ||
      (a.category_name ?? "").toLowerCase().includes(q),
  );
});

onMounted(async () => {
  loading.value = true;
  try {
    await Promise.all([loadApplications(), loadStatusCounts()]);
  } finally {
    loading.value = false;
  }
});

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "numeric" });
}

async function handleDecideApplication(applicationId: number, decision: "approve" | "reject") {
  decidingApplicationId.value = applicationId;
  try {
    if (decision === "approve") await applicationsApi.approveApplication(applicationId);
    else await applicationsApi.rejectApplication(applicationId);
    await Promise.all([loadApplications(applicationsPage.page), loadStatusCounts()]);
  } finally {
    decidingApplicationId.value = null;
  }
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
          placeholder="Поиск по имени ученика или номеру телефона..."
          class="input py-2.5 pl-9 pr-3 text-sm"
        />
      </div>

      <div class="inline-flex flex-wrap overflow-hidden rounded-lg border border-line">
        <button
          type="button"
          class="min-h-11 px-3 py-2 text-xs font-medium transition-colors"
          :class="statusFilter === 'all' ? 'bg-moss text-moss-fg' : 'text-ink-2 hover:bg-paper-2 hover:text-ink'"
          @click="setStatusFilter('all')"
        >
          Все заявки ({{ statusCounts.all }})
        </button>
        <button
          v-for="status in STATUSES"
          :key="status"
          type="button"
          class="flex min-h-11 items-center gap-1.5 border-l border-line px-3 py-2 text-xs font-medium transition-colors"
          :class="statusFilter === status ? 'bg-moss text-moss-fg' : 'text-ink-2 hover:bg-paper-2 hover:text-ink'"
          @click="setStatusFilter(status)"
        >
          <span class="h-1.5 w-1.5 shrink-0 rounded-full" :class="STATUS_DOT[status]" />
          {{ STATUS_LABEL[status] }} ({{ statusCounts[status] }})
        </button>
      </div>
    </div>

    <div v-if="loading" class="space-y-2">
      <div v-for="i in 6" :key="i" class="h-20 animate-pulse rounded-xl bg-paper-2" />
    </div>

    <template v-else>
      <ul class="space-y-2">
        <li
          v-for="application in filteredApplications"
          :key="application.id"
          class="card flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <div class="min-w-0 flex-1">
            <p class="font-medium text-ink">{{ application.student_name ?? "—" }}</p>
            <div class="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-3">
              <span class="flex items-center gap-1">
                <Calendar :size="13" :stroke-width="1.8" />
                {{ formatDate(application.created_at) }}
              </span>
              <span v-if="application.category_name" class="text-ink-2">{{ application.category_name }}</span>
              <span v-if="application.student_phone" class="flex items-center gap-1">
                <Phone :size="13" :stroke-width="1.8" />
                {{ application.student_phone }}
              </span>
            </div>
          </div>

          <div class="flex shrink-0 flex-wrap items-center gap-2">
            <template v-if="application.status === 'pending'">
              <button
                type="button"
                class="min-h-11 rounded-lg border border-clay/30 px-3 py-1.5 text-xs font-medium text-clay transition-colors hover:bg-clay/10 disabled:cursor-not-allowed disabled:opacity-50"
                :disabled="decidingApplicationId === application.id"
                @click="handleDecideApplication(application.id, 'reject')"
              >
                <X :size="14" :stroke-width="2" class="mr-1 inline" />
                Отклонить
              </button>
              <button
                type="button"
                class="min-h-11 rounded-lg bg-moss px-3 py-1.5 text-xs font-medium text-moss-fg transition-colors hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
                :disabled="decidingApplicationId === application.id"
                @click="handleDecideApplication(application.id, 'approve')"
              >
                <Check :size="14" :stroke-width="2" class="mr-1 inline" />
                Одобрить
              </button>
            </template>
            <span
              class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium"
              :class="STATUS_BADGE_CLASS[application.status]"
            >
              <span class="h-1.5 w-1.5 rounded-full" :class="STATUS_DOT[application.status]" />
              {{ STATUS_LABEL[application.status] }}
            </span>
          </div>
        </li>
        <li v-if="!filteredApplications.length" class="rounded-xl border border-dashed border-line py-10 text-center text-sm text-ink-3">
          Ничего не найдено.
        </li>
      </ul>

      <PaginationControls
        :page="applicationsPage.page"
        :pages="applicationsPage.pages"
        :total="applicationsPage.total"
        @change="loadApplications"
      />
    </template>
  </div>
</template>
