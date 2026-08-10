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
</script>

<template>
  <span v-if="status === 'pending'" class="badge bg-marigold/20 text-ink">
    <span class="relative flex h-1.5 w-1.5">
      <span class="motion-safe:animate-ping absolute inline-flex h-full w-full rounded-full bg-marigold opacity-75" />
      <span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-marigold" />
    </span>
    {{ label }}
  </span>
  <span v-else-if="status === 'approved'" class="badge bg-moss/15 text-moss">
    <svg class="h-3 w-3" viewBox="0 0 20 20" fill="currentColor">
      <path
        fill-rule="evenodd"
        d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
        clip-rule="evenodd"
      />
    </svg>
    {{ label }}
  </span>
  <BaseBadge v-else :tone="status === 'rejected' ? 'danger' : 'neutral'">{{ label }}</BaseBadge>
</template>
