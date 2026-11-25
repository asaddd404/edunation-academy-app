<script setup lang="ts">
import { ref, watch } from "vue";

import { updateLesson } from "@/api/lessons";
import { updateSection } from "@/api/sections";
import { describeApiError } from "@/utils/apiError";

/**
 * «Вопросов в одной попытке»: lets a test's bank be bigger than one attempt.
 * Each attempt then gets its own selection, avoiding the previous attempt's
 * questions where the bank allows, so a retake is not the same sheet with
 * one answer changed. Off ("Все вопросы") keeps the old behaviour.
 */
const props = defineProps<{ lessonId?: number; sectionId?: number; value: number | null; total: number }>();
const emit = defineEmits<{ saved: [value: number | null] }>();

const limited = ref(props.value !== null);
const count = ref(props.value ?? Math.max(1, Math.min(props.total - 1, 5)));
const state = ref<"idle" | "saving" | "saved" | "error">("idle");
const error = ref("");
let timer: ReturnType<typeof setTimeout> | null = null;
let lastSent: number | null = props.value;

function current(): number | null {
  return limited.value ? Math.max(1, Math.min(200, Math.round(count.value) || 1)) : null;
}

async function save() {
  const value = current();
  if (value === lastSent) return;
  state.value = "saving";
  try {
    const body = { questions_per_attempt: value ?? 0 };
    if (props.lessonId) await updateLesson(props.lessonId, body);
    else await updateSection(props.sectionId!, body);
    lastSent = value;
    state.value = "saved";
    emit("saved", value);
  } catch (e) {
    state.value = "error";
    error.value = describeApiError(e, "Не удалось сохранить.");
  }
}

watch([limited, count], () => {
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => void save(), 600);
});

function step(delta: number) {
  count.value = Math.max(1, Math.min(200, (Math.round(count.value) || 1) + delta));
}
</script>

<template>
  <section class="space-y-2 rounded-xl border border-line bg-paper-2/50 p-3 sm:p-4" aria-label="Вопросов в одной попытке">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <p class="font-semibold text-ink">Вопросов в одной попытке</p>
      <span v-if="state === 'saving'" class="text-sm text-ink-3" role="status">Сохраняется…</span>
      <span v-else-if="state === 'saved'" class="text-sm text-moss" role="status">✓ Сохранено</span>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <button
        type="button"
        class="min-h-11 rounded-xl border-2 px-4 font-semibold"
        :class="!limited ? 'border-moss bg-moss/10 text-moss' : 'border-line-strong text-ink-2'"
        :aria-pressed="!limited"
        @click="limited = false"
      >
        Все вопросы ({{ total }})
      </button>
      <button
        type="button"
        class="min-h-11 rounded-xl border-2 px-4 font-semibold"
        :class="limited ? 'border-moss bg-moss/10 text-moss' : 'border-line-strong text-ink-2'"
        :aria-pressed="limited"
        @click="limited = true"
      >
        Случайные
      </button>
      <span v-if="limited" class="flex items-center gap-2">
        <button type="button" class="flex h-11 w-11 items-center justify-center rounded-lg border-2 border-line-strong text-xl" aria-label="Меньше вопросов" @click="step(-1)">−</button>
        <span class="min-w-8 text-center text-xl font-bold" aria-live="polite">{{ count }}</span>
        <button type="button" class="flex h-11 w-11 items-center justify-center rounded-lg border-2 border-line-strong text-xl" aria-label="Больше вопросов" @click="step(1)">+</button>
        <span class="text-ink-2">из {{ total }}</span>
      </span>
    </div>
    <p class="text-sm text-ink-3">
      <template v-if="!limited">Ученик каждый раз отвечает на все вопросы по порядку.</template>
      <template v-else-if="count >= total">
        Сейчас вопросов не больше, чем в попытке, — порядок будет меняться, но набор одинаковый. Добавьте ещё вопросы, чтобы попытки отличались.
      </template>
      <template v-else>
        Каждая попытка берёт {{ count }} из {{ total }} вопросов, по возможности не те, что были в прошлый раз. Так ответы не получится запомнить.
      </template>
    </p>
    <p v-if="state === 'error'" class="text-sm text-red-700 dark:text-red-400" role="alert">{{ error }}</p>
  </section>
</template>
