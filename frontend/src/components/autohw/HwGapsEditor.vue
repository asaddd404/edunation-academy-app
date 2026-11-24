<script setup lang="ts">
import { computed, ref, useId } from "vue";

import type { HwTaskData } from "@/types/autoHomework";
import { makeGap, parseGapTemplate, removeGap, serializeGapTemplate, setGapAnswers, tokenize } from "@/utils/hwTasks";

/**
 * Fill-the-gaps editor. The text is stored with the gaps in square
 * brackets ("Абай родился в [1845] году"), but the teacher doesn't need to
 * know that: they paste the text and click the words that should become
 * gaps. The brackets stay visible in the text box for whoever prefers to
 * type them.
 */
const props = defineProps<{ data: HwTaskData }>();
const textId = useId();

const parsed = computed(() => parseGapTemplate(props.data.text ?? ""));
const gapCount = computed(() => parsed.value.segments.filter((s) => "gap" in s).length);

const pieces = computed(() =>
  parsed.value.segments.map((seg, segIndex) =>
    "t" in seg
      ? { segIndex, gap: null as null | { n: number; answers: string[] }, tokens: tokenize(seg.t) }
      : { segIndex, gap: { n: seg.gap + 1, answers: seg.answers }, tokens: [] },
  ),
);

function write(segments: ReturnType<typeof parseGapTemplate>["segments"]) {
  props.data.text = serializeGapTemplate(segments);
}

function toWordGap(segIndex: number, tokenIndex: number) {
  write(makeGap(parsed.value.segments, segIndex, tokenIndex));
}

function toText(segIndex: number) {
  write(removeGap(parsed.value.segments, segIndex));
}

const newVariant = ref<Record<number, string>>({});

function addVariant(segIndex: number, answers: string[]) {
  const value = (newVariant.value[segIndex] ?? "").trim().replace(/[[\]|]/g, "");
  if (!value || answers.includes(value)) return;
  write(setGapAnswers(parsed.value.segments, segIndex, [...answers, value]));
  newVariant.value[segIndex] = "";
}

function dropVariant(segIndex: number, answers: string[], index: number) {
  if (answers.length <= 1) return;
  write(setGapAnswers(parsed.value.segments, segIndex, answers.filter((_, i) => i !== index)));
}

const gapRows = computed(() => pieces.value.filter((p) => p.gap));
</script>

<template>
  <div class="space-y-4">
    <div class="space-y-1.5">
      <label :for="textId" class="block font-medium text-ink">Текст задания</label>
      <textarea
        :id="textId"
        v-model="data.text"
        rows="4"
        class="input text-base leading-relaxed"
        placeholder="Вставьте или напишите текст. Например: Абай Кунанбаев родился в 1845 году."
      />
      <p class="text-sm text-ink-3">Слова в квадратных скобках [ ] — это пропуски. Проще отметить их кнопками ниже.</p>
    </div>

    <div v-if="parsed.error" class="rounded-xl bg-red-50 dark:bg-red-500/10 px-4 py-3 text-red-700 dark:text-red-400" role="alert">
      {{ parsed.error }} Исправьте скобки в тексте выше.
    </div>

    <div v-else-if="data.text" class="space-y-2">
      <p class="rounded-xl bg-moss/10 px-4 py-3 text-moss">
        <b>Нажмите на слово</b> — оно станет пропуском. Нажмите ещё раз, чтобы вернуть его.
      </p>
      <div class="flex flex-wrap items-center gap-x-1 gap-y-2 rounded-xl border-2 border-line-strong bg-paper p-4 text-lg leading-loose">
        <template v-for="piece in pieces" :key="piece.segIndex">
          <button
            v-if="piece.gap"
            type="button"
            class="rounded-lg border-2 border-dashed border-amber-600 bg-amber-100 px-2 font-semibold text-amber-950 dark:bg-amber-400/20 dark:text-amber-100"
            :aria-label="`Пропуск ${piece.gap.n}: ${piece.gap.answers[0]}. Нажмите, чтобы убрать пропуск`"
            @click="toText(piece.segIndex)"
          >
            {{ piece.gap.answers[0] }}
          </button>
          <template v-else>
            <template v-for="(token, ti) in piece.tokens" :key="ti">
              <button
                v-if="token.word"
                type="button"
                class="rounded-md px-0.5 transition-colors hover:bg-moss/15"
                @click="toWordGap(piece.segIndex, ti)"
              >
                {{ token.text }}
              </button>
              <span v-else class="whitespace-pre-wrap">{{ token.text }}</span>
            </template>
          </template>
        </template>
      </div>
    </div>

    <div v-if="!parsed.error && gapCount" class="space-y-2">
      <p class="font-medium text-ink">Пропуски и правильные ответы ({{ gapCount }})</p>
      <div v-for="row in gapRows" :key="row.segIndex" class="space-y-2 rounded-xl bg-paper-2 p-3">
        <div class="flex flex-wrap items-center gap-2">
          <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-moss text-sm font-bold text-moss-fg">{{ row.gap!.n }}</span>
          <span class="text-ink-2">Верно:</span>
          <span
            v-for="(answer, ai) in row.gap!.answers"
            :key="ai"
            class="inline-flex items-center gap-1 rounded-full bg-paper px-3 py-1 font-medium text-ink ring-1 ring-line"
          >
            {{ answer }}
            <button
              v-if="row.gap!.answers.length > 1"
              type="button"
              class="-mr-1 flex h-7 w-7 items-center justify-center rounded-full text-ink-3 hover:bg-red-50 dark:hover:bg-red-500/10 hover:text-red-700"
              :aria-label="`Убрать вариант ${answer}`"
              @click="dropVariant(row.segIndex, row.gap!.answers, ai)"
            >
              ×
            </button>
          </span>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <input
            v-model="newVariant[row.segIndex]"
            class="input min-h-11 max-w-xs text-base"
            :aria-label="`Ещё один верный вариант для пропуска ${row.gap!.n}`"
            placeholder="Ещё верный вариант, например «Семей»"
            @keydown.enter.prevent="addVariant(row.segIndex, row.gap!.answers)"
          />
          <button type="button" class="btn-ghost min-h-11" @click="addVariant(row.segIndex, row.gap!.answers)">+ Добавить вариант</button>
        </div>
      </div>
    </div>

    <div class="space-y-2">
      <label class="flex min-h-11 cursor-pointer items-center gap-3">
        <input v-model="data.allow_typo" type="checkbox" class="h-6 w-6 accent-moss" />
        <span>Прощать одну опечатку <span class="text-ink-3">— если важен факт, а не орфография (кроме чисел)</span></span>
      </label>
      <label class="flex min-h-11 cursor-pointer items-center gap-3">
        <input v-model="data.case_sensitive" type="checkbox" class="h-6 w-6 accent-moss" />
        <span>Учитывать заглавные буквы <span class="text-ink-3">— обычно не нужно</span></span>
      </label>
    </div>
  </div>
</template>
