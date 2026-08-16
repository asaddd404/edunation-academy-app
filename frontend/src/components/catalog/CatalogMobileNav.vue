<script setup lang="ts">
import { Check, ChevronLeft, ChevronRight, FileText, Folder, Lock, Search } from "@lucide/vue";
import { computed } from "vue";

import type { MillerItem } from "@/components/catalog/MillerColumn.vue";

/**
 * Phone view of the catalog: one level at a time instead of the desktop's
 * side-by-side columns, which on a narrow screen collapse into a horizontal
 * scroll that is easy to get lost in.
 *
 * The step is derived from the parent's selection (which itself lives in the
 * URL query), so "back" is a normal route change and the hardware/browser
 * back button works without any extra handling here.
 */
const props = defineProps<{
  /** Levels from root to current; the last one is what gets rendered. */
  levels: { title: string; items: MillerItem[]; loading?: boolean; emptyText?: string }[];
  /** Breadcrumb labels for the levels already drilled into. */
  crumbs: string[];
  search: string;
}>();

const emit = defineEmits<{
  (e: "select", itemId: number | string): void;
  (e: "back"): void;
  (e: "update:search", value: string): void;
}>();

const current = computed(() => props.levels[props.levels.length - 1]);
const canGoBack = computed(() => props.levels.length > 1);

const filtered = computed(() => {
  const query = props.search.trim().toLowerCase();
  if (!query) return current.value.items;
  return current.value.items.filter((item) => item.label.toLowerCase().includes(query));
});
</script>

<template>
  <div>
    <!-- Sticky header: stays reachable while the list scrolls, so "back" is
         always one thumb-tap away rather than a scroll to the top. -->
    <div class="sticky top-0 z-20 -mx-4 border-b border-line bg-paper/95 px-4 pb-3 pt-2 backdrop-blur">
      <div class="flex min-h-12 items-center gap-2">
        <button
          v-if="canGoBack"
          type="button"
          class="-ml-2 flex h-12 w-12 shrink-0 items-center justify-center rounded-xl text-ink-2 transition-colors duration-200 hover:bg-paper-2 hover:text-ink"
          aria-label="Назад"
          @click="emit('back')"
        >
          <ChevronLeft :size="22" :stroke-width="2" />
        </button>
        <h1 class="min-w-0 flex-1 truncate font-display text-lg font-semibold text-ink">
          {{ current.title }}
        </h1>
      </div>

      <nav v-if="crumbs.length" class="mt-0.5 flex items-center gap-1 overflow-x-auto text-xs text-ink-3">
        <template v-for="(crumb, i) in crumbs" :key="i">
          <ChevronRight v-if="i > 0" :size="12" :stroke-width="2" class="shrink-0" />
          <span class="whitespace-nowrap">{{ crumb }}</span>
        </template>
      </nav>

      <label class="relative mt-3 block">
        <Search :size="16" :stroke-width="1.8" class="absolute left-3 top-1/2 -translate-y-1/2 text-ink-3" />
        <input
          :value="search"
          type="search"
          class="input min-h-12 pl-9"
          :placeholder="`Поиск: ${current.title.toLowerCase()}`"
          @input="emit('update:search', ($event.target as HTMLInputElement).value)"
        />
      </label>
    </div>

    <!-- Keyed on depth so each level mounts fresh and plays the slide-in.
         Deliberately a CSS animation on a keyed element rather than
         <Transition mode="out-in">: that mode holds the outgoing level on
         screen until its `transitionend` fires, so a single missed event
         (a backgrounded tab that stops compositing, for one) leaves the
         catalog permanently showing the previous level's items. An
         animation has no such gate -- the new level is in the DOM at once. -->
    <div :key="levels.length" class="motion-safe:animate-drill-in space-y-2 pt-4">
        <div v-if="current.loading" class="space-y-2">
          <div v-for="n in 5" :key="n" class="h-14 animate-pulse rounded-xl bg-paper-2" />
        </div>

        <p v-else-if="!filtered.length" class="card p-6 text-center text-sm text-ink-3">
          {{ search.trim() ? "Ничего не найдено" : (current.emptyText ?? "Пусто") }}
        </p>

        <button
          v-for="item in filtered"
          v-else
          :key="item.id"
          type="button"
          class="card flex min-h-14 w-full items-center gap-3 p-3 text-left transition-all duration-200 ease-out active:scale-[0.99]"
          :class="item.locked ? 'opacity-60' : 'hover:border-moss/40 hover:shadow-sm'"
          :disabled="item.locked"
          @click="emit('select', item.id)"
        >
          <span
            class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl"
            :class="item.kind === 'leaf' ? 'bg-moss/10 text-moss' : 'bg-paper-2 text-ink-2'"
          >
            <Lock v-if="item.locked" :size="17" :stroke-width="1.8" />
            <Folder v-else-if="item.kind === 'folder'" :size="17" :stroke-width="1.8" />
            <FileText v-else :size="17" :stroke-width="1.8" />
          </span>

          <span class="min-w-0 flex-1">
            <span class="block truncate font-medium text-ink">{{ item.label }}</span>
            <span v-if="item.meta" class="block truncate text-xs text-ink-3">{{ item.meta }}</span>
          </span>

          <Check v-if="item.done" :size="17" :stroke-width="2.2" class="shrink-0 text-moss" />
          <ChevronRight v-if="!item.locked" :size="17" :stroke-width="1.8" class="shrink-0 text-ink-3" />
        </button>
      </div>
  </div>
</template>
