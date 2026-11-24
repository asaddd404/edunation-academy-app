<script setup lang="ts">
import { computed, useId } from "vue";

import FilePicker from "@/components/ui/FilePicker.vue";
import type { HwAnswer, HwTaskView } from "@/types/autoHomework";
import { pluralPoints, wordCount } from "@/utils/hwTasks";

/**
 * One task as the student answers it. Writes into `answer` (the attempt's
 * answer object for this task) directly; the runner around it autosaves.
 */
const props = defineProps<{
  task: HwTaskView;
  answer: HwAnswer;
  number: number;
  disabled?: boolean;
  uploading?: boolean;
}>();
const emit = defineEmits<{ upload: [file: File] }>();
const uid = useId();

const LETTERS = "АБВГДЕЖЗИКЛМ";

// fill-the-gaps
function gapValue(i: number): string {
  return props.answer.gaps?.[i] ?? "";
}
function setGap(i: number, value: string) {
  const gaps = (props.answer.gaps ?? []).slice();
  while (gaps.length <= i) gaps.push("");
  gaps[i] = value;
  props.answer.gaps = gaps;
}
function gapSize(i: number): number {
  return Math.max(6, gapValue(i).length + 2);
}

// multi
function toggleMulti(id: string) {
  const set = new Set(props.answer.options ?? []);
  if (set.has(id)) set.delete(id);
  else set.add(id);
  props.answer.options = [...set];
}

// match
function setPair(leftId: string, rightId: string) {
  props.answer.pairs = { ...(props.answer.pairs ?? {}), [leftId]: rightId };
  if (!rightId) delete props.answer.pairs[leftId];
}
const usedRights = computed(() => Object.values(props.answer.pairs ?? {}));

// order: starts as shown, so an untouched list still counts what is in place
const order = computed<string[]>(() => {
  const ids = (props.task.items ?? []).map((i) => i.id);
  const current = (props.answer.order ?? []).filter((id) => ids.includes(id));
  return current.length === ids.length ? current : ids;
});
const itemText = computed(() => Object.fromEntries((props.task.items ?? []).map((i) => [i.id, i.text])));
function moveItem(index: number, delta: number) {
  const next = order.value.slice();
  const j = index + delta;
  if (j < 0 || j >= next.length) return;
  [next[index], next[j]] = [next[j], next[index]];
  props.answer.order = next;
}

const words = computed(() => wordCount(props.answer.text));
</script>

<template>
  <section class="space-y-4 rounded-2xl border border-line bg-paper p-4 sm:p-5" :aria-labelledby="`${uid}-title`">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <h3 :id="`${uid}-title`" class="font-bold text-ink">Задание {{ number }}</h3>
      <span class="text-sm text-ink-3">{{ task.points }} {{ pluralPoints(task.points) }}</span>
    </div>
    <p v-if="task.prompt" class="whitespace-pre-line text-base leading-relaxed text-ink">{{ task.prompt }}</p>

    <!-- Fill the gaps: inputs inside the text -->
    <p v-if="task.type === 'gaps'" class="text-lg leading-[2.6]">
      <template v-for="(seg, i) in task.segments" :key="i">
        <span v-if="'t' in seg" class="whitespace-pre-wrap">{{ seg.t }}</span>
        <input
          v-else
          :value="gapValue(seg.gap)"
          :size="gapSize(seg.gap)"
          :disabled="disabled"
          :aria-label="`Пропуск ${seg.gap + 1}`"
          autocomplete="off"
          autocapitalize="off"
          spellcheck="false"
          class="mx-1 inline-block h-11 max-w-full rounded-lg border-2 border-moss/40 bg-paper px-2 align-middle text-base focus:border-moss focus:outline-none focus:ring-2 focus:ring-moss/30"
          @input="setGap(seg.gap, ($event.target as HTMLInputElement).value)"
        />
      </template>
    </p>

    <!-- One answer -->
    <div v-else-if="task.type === 'single'" class="space-y-2" role="radiogroup" :aria-labelledby="`${uid}-title`">
      <label
        v-for="(o, i) in task.options"
        :key="o.id"
        class="flex min-h-14 cursor-pointer items-center gap-3 rounded-xl border-2 px-4 py-2 transition-colors"
        :class="answer.option === o.id ? 'border-moss bg-moss/5' : 'border-line hover:border-moss/40'"
      >
        <input v-model="answer.option" type="radio" :name="`${uid}-opt`" :value="o.id" :disabled="disabled" class="h-5 w-5 accent-moss" />
        <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-paper-2 text-sm font-bold text-ink-2">{{ LETTERS[i] }}</span>
        <span class="text-base">{{ o.text }}</span>
      </label>
    </div>

    <!-- Several answers -->
    <div v-else-if="task.type === 'multi'" class="space-y-2">
      <p class="text-sm text-ink-3">Отметьте все верные варианты</p>
      <label
        v-for="(o, i) in task.options"
        :key="o.id"
        class="flex min-h-14 cursor-pointer items-center gap-3 rounded-xl border-2 px-4 py-2 transition-colors"
        :class="answer.options?.includes(o.id) ? 'border-moss bg-moss/5' : 'border-line hover:border-moss/40'"
      >
        <input type="checkbox" :checked="answer.options?.includes(o.id)" :disabled="disabled" class="h-5 w-5 accent-moss" @change="toggleMulti(o.id)" />
        <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-paper-2 text-sm font-bold text-ink-2">{{ LETTERS[i] }}</span>
        <span class="text-base">{{ o.text }}</span>
      </label>
    </div>

    <!-- Short answer -->
    <div v-else-if="task.type === 'short'">
      <label :for="`${uid}-short`" class="sr-only">Ваш ответ</label>
      <input
        :id="`${uid}-short`"
        v-model="answer.text"
        :disabled="disabled"
        autocomplete="off"
        spellcheck="false"
        class="input min-h-12 max-w-md text-base"
        placeholder="Ваш ответ"
      />
    </div>

    <!-- Matching -->
    <div v-else-if="task.type === 'match'" class="space-y-2">
      <div v-for="left in task.lefts" :key="left.id" class="flex flex-col gap-1.5 rounded-xl bg-paper-2/60 p-3 sm:flex-row sm:items-center sm:gap-3">
        <span class="font-medium text-ink sm:w-2/5">{{ left.text }}</span>
        <select
          :value="answer.pairs?.[left.id] ?? ''"
          :disabled="disabled"
          :aria-label="`Пара для «${left.text}»`"
          class="input min-h-12 text-base sm:flex-1"
          @change="setPair(left.id, ($event.target as HTMLSelectElement).value)"
        >
          <option value="">— выберите —</option>
          <option v-for="right in task.rights" :key="right.id" :value="right.id">
            {{ right.text }}{{ usedRights.includes(right.id) && answer.pairs?.[left.id] !== right.id ? " (уже выбрано)" : "" }}
          </option>
        </select>
      </div>
    </div>

    <!-- True / false -->
    <div v-else-if="task.type === 'tf'" class="flex flex-wrap gap-2" role="radiogroup">
      <button
        v-for="value in [true, false]"
        :key="String(value)"
        type="button"
        role="radio"
        :aria-checked="answer.value === value"
        :disabled="disabled"
        class="min-h-14 min-w-36 rounded-xl border-2 px-6 text-lg font-semibold transition-colors"
        :class="answer.value === value ? 'border-moss bg-moss/10 text-moss' : 'border-line hover:border-moss/40'"
        @click="answer.value = value"
      >
        {{ value ? "Верно" : "Неверно" }}
      </button>
    </div>

    <!-- Ordering -->
    <ol v-else-if="task.type === 'order'" class="space-y-2">
      <li v-for="(id, i) in order" :key="id" class="flex items-center gap-2 rounded-xl border-2 border-line bg-paper p-2 pl-3">
        <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-moss/10 font-bold text-moss">{{ i + 1 }}</span>
        <span class="min-w-0 flex-1 text-base">{{ itemText[id] }}</span>
        <button type="button" class="min-h-11 rounded-lg border border-line px-3 text-sm font-medium disabled:opacity-40" :disabled="disabled || i === 0" :aria-label="`Поднять «${itemText[id]}» выше`" @click="moveItem(i, -1)">↑</button>
        <button
          type="button"
          class="min-h-11 rounded-lg border border-line px-3 text-sm font-medium disabled:opacity-40"
          :disabled="disabled || i === order.length - 1"
          :aria-label="`Опустить «${itemText[id]}» ниже`"
          @click="moveItem(i, 1)"
        >
          ↓
        </button>
      </li>
    </ol>

    <!-- Essay -->
    <div v-else-if="task.type === 'essay'" class="space-y-2">
      <label :for="`${uid}-essay`" class="sr-only">Ваш ответ</label>
      <textarea :id="`${uid}-essay`" v-model="answer.text" :disabled="disabled" rows="7" class="input text-base leading-relaxed" placeholder="Напишите ответ здесь" />
      <p class="text-sm" :class="task.min_words && words < task.min_words ? 'text-amber-700 dark:text-amber-300' : 'text-ink-3'">
        Слов: {{ words }}<template v-if="task.min_words"> из {{ task.min_words }} минимум</template>
      </p>
      <div v-if="task.criteria?.length" class="rounded-xl bg-paper-2 p-3 text-sm text-ink-2">
        <p class="mb-1 font-semibold text-ink">Как будет оцениваться:</p>
        <ul class="list-disc space-y-0.5 pl-5">
          <li v-for="(c, i) in task.criteria" :key="i">{{ c.text }} — {{ c.points }} {{ pluralPoints(c.points) }}</li>
        </ul>
      </div>
    </div>

    <!-- File -->
    <div v-else-if="task.type === 'file'" class="space-y-2">
      <FilePicker
        :file="null"
        accept=".jpg,.jpeg,.png,.pdf,.txt,.doc,.docx"
        :label="answer.file_name ? 'Заменить файл' : 'Прикрепить фото или файл'"
        :disabled="disabled || uploading"
        @pick="emit('upload', $event)"
        @clear="() => undefined"
      />
      <p v-if="uploading" class="text-sm text-ink-3" role="status">Загружается…</p>
      <p v-else-if="answer.file_name" class="text-sm text-moss" role="status">✓ Прикреплено: {{ answer.file_name }}</p>
      <p class="text-sm text-ink-3">Фото, PDF или Word, до 10 МБ</p>
    </div>
  </section>
</template>
