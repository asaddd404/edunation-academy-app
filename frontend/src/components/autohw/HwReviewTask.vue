<script setup lang="ts">
import { computed } from "vue";

import type { HwReviewBlock } from "@/types/autoHomework";
import { formatPoints } from "@/utils/hwTasks";

/**
 * One task after the key has opened (student's review) or in the teacher's
 * view of a student's work: what was answered, what was right, the points.
 */
const props = defineProps<{ block: HwReviewBlock; number: number }>();

const t = computed(() => props.block.task);
const a = computed(() => props.block.answer ?? {});
const c = computed(() => props.block.correct ?? {});
const manual = computed(() => t.value.type === "essay" || t.value.type === "file");
const full = computed(() => props.block.earned != null && props.block.earned >= props.block.max - 1e-9);
const none = computed(() => props.block.earned != null && props.block.earned <= 0);

const rightText = computed(() => Object.fromEntries((t.value.rights ?? []).map((r) => [r.id, r.text])));
const itemText = computed(() => Object.fromEntries((t.value.items ?? []).map((i) => [i.id, i.text])));

function gapCorrect(i: number): boolean {
  return props.block.items.find((it) => it.key === `g${i}`)?.correct === true;
}
</script>

<template>
  <section
    class="space-y-3 rounded-2xl border bg-paper p-4 sm:p-5"
    :class="manual ? 'border-line' : full ? 'border-moss/40' : 'border-red-300 dark:border-red-500/40'"
    :aria-label="`Задание ${number}`"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3 class="font-bold text-ink">Задание {{ number }}</h3>
      <span
        class="rounded-full px-3 py-1 text-sm font-bold"
        :class="
          block.earned == null
            ? 'bg-amber-100 text-amber-900 dark:bg-amber-400/15 dark:text-amber-200'
            : full
              ? 'bg-moss/15 text-moss'
              : none
                ? 'bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400'
                : 'bg-amber-100 text-amber-900 dark:bg-amber-400/15 dark:text-amber-200'
        "
      >
        <template v-if="block.earned == null">Ожидает проверки учителем</template>
        <template v-else>{{ full ? "✓" : none ? "✗" : "≈" }} {{ formatPoints(block.earned) }} из {{ formatPoints(block.max) }}</template>
      </span>
    </div>
    <p v-if="t.prompt" class="whitespace-pre-line text-ink">{{ t.prompt }}</p>

    <!-- Gaps -->
    <p v-if="t.type === 'gaps'" class="text-base leading-loose">
      <template v-for="(seg, i) in t.segments" :key="i">
        <span v-if="'t' in seg" class="whitespace-pre-wrap">{{ seg.t }}</span>
        <template v-else>
          <span
            class="mx-0.5 rounded-md px-1.5 py-0.5 font-semibold"
            :class="gapCorrect(seg.gap) ? 'bg-moss/15 text-moss' : 'bg-red-50 dark:bg-red-500/10 text-red-700 dark:text-red-400 line-through decoration-2'"
          >{{ a.gaps?.[seg.gap] || "—" }}</span>
          <span v-if="!gapCorrect(seg.gap)" class="mx-0.5 rounded-md bg-moss/15 px-1.5 py-0.5 font-semibold text-moss">{{ c.gaps?.[seg.gap]?.[0] }}</span>
        </template>
      </template>
    </p>

    <!-- Choice -->
    <ul v-else-if="t.type === 'single' || t.type === 'multi'" class="space-y-1.5">
      <li
        v-for="o in t.options"
        :key="o.id"
        class="flex items-center gap-2 rounded-xl px-3 py-2"
        :class="c.options?.includes(o.id) ? 'bg-moss/10' : (t.type === 'single' ? a.option === o.id : a.options?.includes(o.id)) ? 'bg-red-50 dark:bg-red-500/10' : 'bg-paper-2/60'"
      >
        <span class="w-6 text-center font-bold" :class="c.options?.includes(o.id) ? 'text-moss' : 'text-red-700 dark:text-red-400'">
          {{ c.options?.includes(o.id) ? "✓" : (t.type === "single" ? a.option === o.id : a.options?.includes(o.id)) ? "✗" : "" }}
        </span>
        <span class="flex-1">{{ o.text }}</span>
        <span v-if="t.type === 'single' ? a.option === o.id : a.options?.includes(o.id)" class="text-sm text-ink-3">ваш выбор</span>
      </li>
    </ul>

    <!-- Short -->
    <div v-else-if="t.type === 'short'" class="space-y-1">
      <p>Ваш ответ: <b :class="full ? 'text-moss' : 'text-red-700 dark:text-red-400'">{{ a.text || "—" }}</b></p>
      <p v-if="!full">Правильно: <b class="text-moss">{{ c.answers?.join(" или ") }}</b></p>
    </div>

    <!-- Matching -->
    <ul v-else-if="t.type === 'match'" class="space-y-1.5">
      <li v-for="left in t.lefts" :key="left.id" class="rounded-xl bg-paper-2/60 px-3 py-2">
        <span class="font-medium">{{ left.text }}</span> →
        <span :class="a.pairs?.[left.id] === c.pairs?.[left.id] ? 'font-semibold text-moss' : 'text-red-700 dark:text-red-400 line-through'">{{ rightText[a.pairs?.[left.id] ?? ""] || "—" }}</span>
        <span v-if="a.pairs?.[left.id] !== c.pairs?.[left.id]" class="ml-1 font-semibold text-moss">{{ rightText[c.pairs?.[left.id] ?? ""] }}</span>
      </li>
    </ul>

    <!-- True / false -->
    <p v-else-if="t.type === 'tf'">
      Ваш ответ: <b :class="full ? 'text-moss' : 'text-red-700 dark:text-red-400'">{{ a.value === undefined ? "—" : a.value ? "Верно" : "Неверно" }}</b>
      <template v-if="!full"> · Правильно: <b class="text-moss">{{ c.value ? "Верно" : "Неверно" }}</b></template>
    </p>

    <!-- Ordering -->
    <div v-else-if="t.type === 'order'" class="grid gap-3 sm:grid-cols-2">
      <div>
        <p class="mb-1 text-sm font-semibold text-ink-2">Ваш порядок</p>
        <ol class="list-decimal space-y-1 pl-5">
          <li v-for="(id, i) in a.order ?? []" :key="id" :class="c.order?.[i] === id ? 'text-moss' : 'text-red-700 dark:text-red-400'">{{ itemText[id] }}</li>
        </ol>
      </div>
      <div>
        <p class="mb-1 text-sm font-semibold text-ink-2">Правильный порядок</p>
        <ol class="list-decimal space-y-1 pl-5 text-moss">
          <li v-for="id in c.order ?? []" :key="id">{{ itemText[id] }}</li>
        </ol>
      </div>
    </div>

    <!-- Essay -->
    <div v-else-if="t.type === 'essay'" class="whitespace-pre-line rounded-xl bg-paper-2/60 px-4 py-3 leading-relaxed">{{ a.text || "Ответ не написан" }}</div>

    <!-- File -->
    <p v-else-if="t.type === 'file'" class="text-ink-2">{{ a.file_name ? `Прикреплён файл: ${a.file_name}` : "Файл не прикреплён" }}</p>

    <slot />
  </section>
</template>
