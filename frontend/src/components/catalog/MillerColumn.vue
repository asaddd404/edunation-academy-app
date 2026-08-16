<script setup lang="ts">
import { Check, ChevronRight, FileText, Folder, Lock } from "@lucide/vue";

export interface MillerItem {
  id: number | string;
  label: string;
  meta?: string;
  kind: "folder" | "leaf";
  locked?: boolean;
  done?: boolean;
}

defineProps<{
  title: string;
  items: MillerItem[];
  selectedId?: number | string | null;
  loading?: boolean;
  emptyText?: string;
}>();
const emit = defineEmits<{ (e: "select", itemId: number | string): void }>();
</script>

<template>
  <div class="miller-column">
    <h2 class="miller-column-title">{{ title }}</h2>
    <div class="miller-column-card">
      <div v-if="loading" class="space-y-2 p-3">
        <div v-for="n in 4" :key="n" class="h-11 animate-pulse rounded-lg bg-paper-2" />
      </div>
      <p v-else-if="!items.length" class="p-4 text-sm text-ink-3">{{ emptyText ?? "Пусто" }}</p>
      <div
        v-for="item in items"
        v-else
        :key="item.id"
        class="group miller-column-item"
        :class="{ 'miller-column-item-active': selectedId === item.id, 'opacity-50': item.locked }"
        @click="!item.locked && emit('select', item.id)"
      >
        <span class="flex min-w-0 items-center gap-2.5">
          <Lock v-if="item.locked" :size="16" :stroke-width="1.8" class="shrink-0 text-ink-3" />
          <Folder v-else-if="item.kind === 'folder'" :size="16" :stroke-width="1.8" class="shrink-0 text-ink-3" />
          <FileText v-else :size="16" :stroke-width="1.8" class="shrink-0 text-moss" />
          <span class="truncate">{{ item.label }}</span>
        </span>
        <span class="flex shrink-0 items-center gap-2">
          <span v-if="item.meta" class="text-xs text-ink-3">{{ item.meta }}</span>
          <Check v-if="item.done" :size="15" :stroke-width="2.2" class="shrink-0 text-moss" />
          <ChevronRight
            v-if="item.kind === 'folder' && !item.locked"
            :size="15"
            :stroke-width="1.8"
            class="shrink-0 text-ink-3 transition-transform group-hover:translate-x-1"
          />
        </span>
      </div>
    </div>
  </div>
</template>
