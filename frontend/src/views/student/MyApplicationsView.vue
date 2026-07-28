<script setup lang="ts">
import { onMounted } from "vue";

import ApplicationStatusBadge from "@/components/application/ApplicationStatusBadge.vue";
import { useApplicationsStore } from "@/stores/applications";

const applications = useApplicationsStore();

onMounted(() => applications.fetchMine());
</script>

<template>
  <div>
    <h1 class="mb-6 text-2xl font-semibold">Мои заявки</h1>
    <p v-if="!applications.myApplications.length" class="text-fg/60">Заявок пока нет.</p>
    <ul class="space-y-3">
      <li
        v-for="application in applications.myApplications"
        :key="application.id"
        class="flex items-center justify-between rounded-xl border border-fg/10 p-4"
      >
        <span>{{ application.category_name ?? `Категория #${application.category_id}` }}</span>
        <ApplicationStatusBadge :status="application.status" />
      </li>
    </ul>
  </div>
</template>
