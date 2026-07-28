<script setup lang="ts">
import { computed } from "vue";

import BaseBadge from "@/components/ui/BaseBadge.vue";
import type { ApplicationStatus } from "@/types";

const props = defineProps<{ status: ApplicationStatus | null }>();

const label = computed(() => {
  switch (props.status) {
    case "pending":
      return "На рассмотрении";
    case "approved":
      return "Доступно";
    case "rejected":
      return "Отклонено";
    default:
      return "Не подана";
  }
});

const tone = computed(() => {
  switch (props.status) {
    case "pending":
      return "warning";
    case "approved":
      return "success";
    case "rejected":
      return "danger";
    default:
      return "neutral";
  }
});
</script>

<template>
  <BaseBadge :tone="tone">{{ label }}</BaseBadge>
</template>
