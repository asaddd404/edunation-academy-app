<script setup lang="ts">
import BaseButton from "@/components/ui/BaseButton.vue";

defineProps<{ page: number; pages: number; total: number }>();
const emit = defineEmits<{ (e: "change", page: number): void }>();
</script>

<template>
  <div v-if="pages > 1" class="flex flex-wrap items-center justify-between gap-3 pt-1 text-sm text-fg/60">
    <span>Стр. {{ page }} из {{ pages }} · всего {{ total }}</span>
    <div class="flex gap-2">
      <BaseButton variant="secondary" :disabled="page <= 1" @click="emit('change', page - 1)">← Назад</BaseButton>
      <BaseButton variant="secondary" :disabled="page >= pages" @click="emit('change', page + 1)">Вперёд →</BaseButton>
    </div>
  </div>
</template>
