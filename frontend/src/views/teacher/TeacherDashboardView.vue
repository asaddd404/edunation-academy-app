<script setup lang="ts">
import { onMounted, ref } from "vue";

import BaseButton from "@/components/ui/BaseButton.vue";
import { useApplicationsStore } from "@/stores/applications";

const applications = useApplicationsStore();
const decidingId = ref<number | null>(null);

onMounted(() => applications.fetchPending());

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
  <div>
    <h1 class="mb-6 text-2xl font-semibold">Заявки на рассмотрении</h1>
    <p v-if="!applications.pendingForTeacher.length" class="text-fg/60">Новых заявок нет.</p>
    <ul class="space-y-3">
      <li
        v-for="application in applications.pendingForTeacher"
        :key="application.id"
        class="flex flex-col gap-3 rounded-xl border border-fg/10 p-4 sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <p class="font-medium">{{ application.student_name }}</p>
          <p class="text-sm text-fg/60">{{ application.student_phone }} · {{ application.category_name }}</p>
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
  </div>
</template>
