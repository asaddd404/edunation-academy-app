<script setup lang="ts">
import { onMounted, ref } from "vue";

import PageContainer from "@/components/layout/PageContainer.vue";
import PageHeader from "@/components/layout/PageHeader.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import PaginationControls from "@/components/ui/PaginationControls.vue";
import { useApplicationsStore } from "@/stores/applications";

const applications = useApplicationsStore();
const decidingId = ref<number | null>(null);
const loading = ref(true);

onMounted(async () => {
  loading.value = true;
  try {
    await applications.fetchPending();
  } finally {
    loading.value = false;
  }
});

async function handleDecide(id: number, decision: "approve" | "reject") {
  decidingId.value = id;
  try {
    await applications.decide(id, decision);
  } finally {
    decidingId.value = null;
  }
}
</script>

<template>
  <PageContainer>
    <PageHeader title="Заявки на рассмотрении" />

    <div v-if="loading" class="space-y-3">
      <div v-for="i in 3" :key="i" class="h-20 animate-pulse rounded-xl bg-paper-2" />
    </div>

    <div v-else-if="!applications.pendingForTeacher.length" class="card py-12 text-center">
      <p class="text-3xl">🎉</p>
      <p class="mt-3 text-ink-2">Новых заявок нет — все текущие уже рассмотрены.</p>
    </div>

    <template v-else>
      <ul class="space-y-3">
        <li
          v-for="application in applications.pendingForTeacher"
          :key="application.id"
          class="card flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <div>
            <p class="font-medium text-ink">{{ application.student_name }}</p>
            <p class="text-sm text-ink-2">{{ application.student_phone }} · {{ application.category_name }}</p>
          </div>
          <div class="flex gap-2">
            <BaseButton
              variant="secondary"
              :disabled="decidingId === application.id"
              @click="handleDecide(application.id, 'reject')"
            >
              Отклонить
            </BaseButton>
            <BaseButton :disabled="decidingId === application.id" @click="handleDecide(application.id, 'approve')">
              Одобрить
            </BaseButton>
          </div>
        </li>
      </ul>

      <PaginationControls
        :page="applications.pendingPage.page"
        :pages="applications.pendingPage.pages"
        :total="applications.pendingPage.total"
        class="mt-4"
        @change="applications.fetchPending"
      />
    </template>
  </PageContainer>
</template>
