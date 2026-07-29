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
  <span
    v-if="status === 'pending'"
    class="inline-flex items-center gap-1.5 rounded-full border border-amber-500/25 bg-gradient-to-r from-amber-500/15 to-orange-500/10 px-2.5 py-1 text-xs font-medium text-amber-700 dark:text-amber-400"
  >
    <span class="relative flex h-1.5 w-1.5">
      <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-500 opacity-75" />
      <span class="relative inline-flex h-1.5 w-1.5 rounded-full bg-amber-500" />
    </span>
    {{ label }}
  </span>
  <span
    v-else-if="status === 'approved'"
    class="inline-flex items-center gap-1 rounded-full border border-emerald-500/25 bg-gradient-to-r from-emerald-500/15 to-teal-500/10 px-2.5 py-1 text-xs font-medium text-emerald-700 shadow-[0_0_14px_-4px] shadow-emerald-500/50 dark:text-emerald-400"
  >
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
