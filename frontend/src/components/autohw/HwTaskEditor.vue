<script setup lang="ts">
import { computed, useId } from "vue";

import HwGapsEditor from "@/components/autohw/HwGapsEditor.vue";
import type { HwTaskData, HwTaskType } from "@/types/autoHomework";
import { pluralPoints } from "@/utils/hwTasks";

/**
 * The fields of one task, by type. Edits the draft it's given in place;
 * the card around it (HwTaskCard) saves it.
 */
const props = defineProps<{
  type: HwTaskType;
  draft: { prompt: string; data: HwTaskData; points: number };
}>();
const uid = useId();

const promptLabel = computed(
  () =>
    ({
      gaps: "Инструкция для ученика (необязательно)",
      single: "Вопрос",
      multi: "Вопрос",
      short: "Вопрос",
      match: "Задание",
      tf: "Утверждение",
      order: "Задание",
      essay: "Тема или вопрос",
      file: "Что прислать",
    })[props.type],
);

const promptPlaceholder = computed(
  () =>
    ({
      gaps: "Вставьте пропущенные слова",
      single: "Например: какое уравнение является линейным?",
      multi: "Например: какие числа являются корнями x² − 5x + 6 = 0?",
      short: "Например: решите 2x = 16. Чему равен x?",
      match: "Соедините даты и события",
      tf: "Например: у линейного уравнения всегда ровно один корень.",
      order: "Расставьте шаги решения по порядку",
      essay:
        "Например: объясните своими словами, почему у уравнения 0·x = 5 нет корней.",
      file: "Например: сфотографируйте решение задач 1–3 в тетради.",
    })[props.type],
);

const criteriaPoints = computed(() =>
  (props.draft.data.criteria ?? []).reduce(
    (sum, c) => sum + (Number(c.points) || 0),
    0,
  ),
);
const pointsLocked = computed(
  () => props.type === "essay" && (props.draft.data.criteria ?? []).length > 0,
);

function setPoints(delta: number) {
  props.draft.points = Math.min(
    100,
    Math.max(1, (props.draft.points || 1) + delta),
  );
}

// ── list helpers (options, pairs, items, criteria, answers) ──
function move<T>(list: T[], index: number, delta: number) {
  const j = index + delta;
  if (j < 0 || j >= list.length) return;
  [list[index], list[j]] = [list[j], list[index]];
}

function addCriterion() {
  if (!props.draft.data.criteria) props.draft.data.criteria = [];
  props.draft.data.criteria.push({ text: "", points: 2 });
}

function chooseSingle(index: number) {
  (props.draft.data.options ?? []).forEach((o, i) => (o.correct = i === index));
}
</script>

<template>
  <div class="space-y-5">
    <div class="space-y-1.5">
      <label :for="`${uid}-prompt`" class="block font-medium text-ink">{{
        promptLabel
      }}</label>
      <textarea
        v-if="type === 'essay' || type === 'file' || type === 'tf'"
        :id="`${uid}-prompt`"
        v-model="draft.prompt"
        rows="2"
        class="input text-base"
        :placeholder="promptPlaceholder"
      />
      <input
        v-else
        :id="`${uid}-prompt`"
        v-model="draft.prompt"
        class="input min-h-12 text-base"
        :placeholder="promptPlaceholder"
      />
    </div>

    <HwGapsEditor v-if="type === 'gaps'" :data="draft.data" />

    <!-- Choice: one or several correct -->
    <div v-else-if="type === 'single' || type === 'multi'" class="space-y-2">
      <p class="font-medium text-ink">
        Варианты ответа —
        {{
          type === "single"
            ? "отметьте один правильный"
            : "отметьте все правильные"
        }}
      </p>
      <div
        v-for="(option, i) in draft.data.options"
        :key="i"
        class="flex flex-wrap items-center gap-2 rounded-xl border-2 p-2 transition-colors sm:flex-nowrap"
        :class="option.correct ? 'border-moss bg-moss/5' : 'border-line'"
      >
        <label
          class="flex min-h-11 shrink-0 cursor-pointer items-center gap-2 px-2"
        >
          <input
            v-if="type === 'single'"
            type="radio"
            :name="`${uid}-correct`"
            :checked="option.correct"
            class="h-6 w-6 accent-moss"
            :aria-label="`Вариант ${i + 1} правильный`"
            @change="chooseSingle(i)"
          />
          <input
            v-else
            v-model="option.correct"
            type="checkbox"
            class="h-6 w-6 accent-moss"
            :aria-label="`Вариант ${i + 1} правильный`"
          />
          <span
            class="text-sm font-semibold"
            :class="option.correct ? 'text-moss' : 'text-ink-3'"
            >{{ option.correct ? "верный" : "неверный" }}</span
          >
        </label>
        <input
          v-model="option.text"
          class="input min-h-11 min-w-0 flex-1 text-base"
          :aria-label="`Текст варианта ${i + 1}`"
          :placeholder="`Вариант ${i + 1}`"
        />
        <button
          type="button"
          class="min-h-11 rounded-lg px-3 text-sm font-medium text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 disabled:opacity-40"
          :disabled="(draft.data.options?.length ?? 0) <= 2"
          @click="draft.data.options!.splice(i, 1)"
        >
          Убрать
        </button>
      </div>
      <button
        type="button"
        class="min-h-11 rounded-xl border-2 border-dashed border-moss/50 px-4 font-medium text-moss hover:bg-moss/5 disabled:opacity-40"
        :disabled="
          (draft.data.options?.length ?? 0) >= (type === 'single' ? 10 : 12)
        "
        @click="draft.data.options!.push({ text: '', correct: false })"
      >
        + Добавить вариант
      </button>
      <label class="flex min-h-11 cursor-pointer items-center gap-3">
        <input
          v-model="draft.data.shuffle"
          type="checkbox"
          class="h-6 w-6 accent-moss"
        />
        <span>Перемешивать варианты для каждого ученика</span>
      </label>
      <label
        v-if="type === 'multi'"
        class="flex min-h-11 cursor-pointer items-center gap-3"
      >
        <input
          v-model="draft.data.partial"
          type="checkbox"
          class="h-6 w-6 accent-moss"
        />
        <span
          >Давать часть баллов, если отмечено не всё
          <span class="text-ink-3"
            >(за неверную отметку балл снимается)</span
          ></span
        >
      </label>
    </div>

    <!-- Short answer -->
    <div v-else-if="type === 'short'" class="space-y-2">
      <p class="font-medium text-ink">Правильный ответ</p>
      <div
        v-for="(_, i) in draft.data.answers"
        :key="i"
        class="flex items-center gap-2"
      >
        <input
          v-model="draft.data.answers![i]"
          class="input min-h-11 max-w-sm text-base"
          :aria-label="i === 0 ? 'Правильный ответ' : `Ещё верный вариант ${i}`"
          :placeholder="i === 0 ? 'Например: 8' : 'Ещё верный вариант'"
        />
        <button
          v-if="i > 0"
          type="button"
          class="min-h-11 rounded-lg px-3 text-sm font-medium text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10"
          @click="draft.data.answers!.splice(i, 1)"
        >
          Убрать
        </button>
      </div>
      <button
        type="button"
        class="min-h-11 rounded-xl border-2 border-dashed border-moss/50 px-4 font-medium text-moss hover:bg-moss/5 disabled:opacity-40"
        :disabled="(draft.data.answers?.length ?? 0) >= 10"
        @click="draft.data.answers!.push('')"
      >
        + Другой верный вариант
      </button>
      <p class="text-sm text-ink-3">
        Заглавные буквы, лишние пробелы, «ё»/«е» и «1,5»/«1.5» не важны.
      </p>
      <label class="flex min-h-11 cursor-pointer items-center gap-3">
        <input
          v-model="draft.data.allow_typo"
          type="checkbox"
          class="h-6 w-6 accent-moss"
        />
        <span
          >Прощать одну опечатку
          <span class="text-ink-3">(кроме чисел)</span></span
        >
      </label>
    </div>

    <!-- Matching -->
    <div v-else-if="type === 'match'" class="space-y-2">
      <p class="font-medium text-ink">
        Пары: левая часть → правая. Ученик увидит правые части перемешанными.
      </p>
      <div
        v-for="(pair, i) in draft.data.pairs"
        :key="i"
        class="flex items-start gap-2 sm:items-center"
      >
        <span
          class="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-paper-2 font-semibold text-ink-2 sm:mt-0"
          >{{ i + 1 }}</span
        >
        <div
          class="flex min-w-0 flex-1 flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-2"
        >
          <input
            v-model="pair.left"
            class="input min-h-11 min-w-0 flex-1 text-base"
            :aria-label="`Пара ${i + 1}, левая часть`"
            placeholder="Например: 1465 год"
          />
          <span class="hidden text-ink-3 sm:block" aria-hidden="true">→</span>
          <input
            v-model="pair.right"
            class="input min-h-11 min-w-0 flex-1 text-base"
            :aria-label="`Пара ${i + 1}, правая часть`"
            placeholder="Образование Казахского ханства"
          />
        </div>
        <button
          type="button"
          class="min-h-11 rounded-lg px-3 text-sm font-medium text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 disabled:opacity-40"
          :disabled="(draft.data.pairs?.length ?? 0) <= 2"
          @click="draft.data.pairs!.splice(i, 1)"
        >
          Убрать
        </button>
      </div>
      <button
        type="button"
        class="min-h-11 rounded-xl border-2 border-dashed border-moss/50 px-4 font-medium text-moss hover:bg-moss/5 disabled:opacity-40"
        :disabled="(draft.data.pairs?.length ?? 0) >= 12"
        @click="draft.data.pairs!.push({ left: '', right: '' })"
      >
        + Добавить пару
      </button>
    </div>

    <!-- True / false -->
    <div v-else-if="type === 'tf'" class="space-y-2">
      <p class="font-medium text-ink">Как правильно?</p>
      <div class="flex flex-wrap gap-2">
        <button
          v-for="value in [true, false]"
          :key="String(value)"
          type="button"
          class="min-h-12 min-w-32 rounded-xl border-2 px-5 text-base font-semibold transition-colors"
          :class="
            draft.data.correct === value
              ? 'border-moss bg-moss/10 text-moss'
              : 'border-line text-ink-2 hover:border-moss/40'
          "
          :aria-pressed="draft.data.correct === value"
          @click="draft.data.correct = value"
        >
          {{ draft.data.correct === value ? "✓ " : ""
          }}{{ value ? "Верно" : "Неверно" }}
        </button>
      </div>
    </div>

    <!-- Ordering -->
    <div v-else-if="type === 'order'" class="space-y-2">
      <p class="font-medium text-ink">
        Напишите пункты в правильном порядке — ученик получит их перемешанными.
      </p>
      <div
        v-for="(item, i) in draft.data.items"
        :key="i"
        class="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-2"
      >
        <div class="flex min-w-0 flex-1 items-center gap-2">
          <span
            class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-moss/10 font-bold text-moss"
            >{{ i + 1 }}</span
          >
          <input
            v-model="item.text"
            class="input min-h-11 min-w-0 flex-1 text-base"
            :aria-label="`Пункт ${i + 1}`"
            :placeholder="`Пункт ${i + 1}`"
          />
        </div>
        <div class="flex flex-wrap items-center gap-2 pl-11 sm:pl-0">
          <button
            type="button"
            class="min-h-11 rounded-lg border border-line px-3 text-sm font-medium disabled:opacity-40"
            :disabled="i === 0"
            @click="move(draft.data.items!, i, -1)"
          >
            ↑ Выше
          </button>
          <button
            type="button"
            class="min-h-11 rounded-lg border border-line px-3 text-sm font-medium disabled:opacity-40"
            :disabled="i === (draft.data.items?.length ?? 0) - 1"
            @click="move(draft.data.items!, i, 1)"
          >
            ↓ Ниже
          </button>
          <button
            type="button"
            class="min-h-11 rounded-lg px-3 text-sm font-medium text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10 disabled:opacity-40"
            :disabled="(draft.data.items?.length ?? 0) <= 2"
            @click="draft.data.items!.splice(i, 1)"
          >
            Убрать
          </button>
        </div>
      </div>
      <button
        type="button"
        class="min-h-11 rounded-xl border-2 border-dashed border-moss/50 px-4 font-medium text-moss hover:bg-moss/5 disabled:opacity-40"
        :disabled="(draft.data.items?.length ?? 0) >= 12"
        @click="draft.data.items!.push({ text: '' })"
      >
        + Добавить пункт
      </button>
    </div>

    <!-- Essay -->
    <div v-else-if="type === 'essay'" class="space-y-3">
      <div class="flex flex-wrap items-center gap-2">
        <label :for="`${uid}-min`">Не меньше</label>
        <input
          :id="`${uid}-min`"
          v-model.number="draft.data.min_words"
          type="number"
          min="0"
          max="3000"
          inputmode="numeric"
          class="input min-h-11 w-24 text-center text-base"
        />
        <span
          >слов
          <span class="text-ink-3"
            >(ученик увидит счётчик; 0 — без ограничения)</span
          ></span
        >
      </div>
      <div class="space-y-2">
        <p class="font-medium text-ink">
          Критерии оценки
          <span class="font-normal text-ink-3">(необязательно)</span>
        </p>
        <p class="text-sm text-ink-3">
          При проверке вы просто отметите выполненные пункты — баллы посчитаются
          сами.
        </p>
        <div
          v-for="(c, i) in draft.data.criteria"
          :key="i"
          class="flex flex-wrap items-center gap-2 sm:flex-nowrap"
        >
          <input
            v-model="c.text"
            class="input min-h-11 min-w-0 flex-[1_1_100%] text-base sm:flex-[1_1_0%]"
            :aria-label="`Критерий ${i + 1}`"
            placeholder="Например: есть объяснение, а не только ответ"
          />
          <input
            v-model.number="c.points"
            type="number"
            min="1"
            max="100"
            inputmode="numeric"
            class="input min-h-11 w-20 text-center text-base"
            :aria-label="`Баллы за критерий ${i + 1}`"
          />
          <span class="text-ink-3">{{
            pluralPoints(Number(c.points) || 0)
          }}</span>
          <button
            type="button"
            class="min-h-11 rounded-lg px-3 text-sm font-medium text-red-700 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-500/10"
            @click="draft.data.criteria!.splice(i, 1)"
          >
            Убрать
          </button>
        </div>
        <button
          type="button"
          class="min-h-11 rounded-xl border-2 border-dashed border-moss/50 px-4 font-medium text-moss hover:bg-moss/5 disabled:opacity-40"
          :disabled="(draft.data.criteria?.length ?? 0) >= 10"
          @click="addCriterion"
        >
          + Добавить критерий
        </button>
      </div>
    </div>

    <p v-else-if="type === 'file'" class="text-ink-2">
      Ученик прикрепит фото, PDF или документ Word (до 10 МБ). Вы посмотрите
      файл прямо на сайте.
    </p>

    <div class="flex flex-wrap items-center gap-3 border-t border-line pt-4">
      <span class="font-medium text-ink">Баллы за задание:</span>
      <template v-if="pointsLocked">
        <span class="text-lg font-bold">{{ criteriaPoints }}</span>
        <span class="text-ink-3">— сумма критериев</span>
      </template>
      <template v-else>
        <span class="flex items-center gap-2">
          <button
            type="button"
            class="flex h-11 w-11 items-center justify-center rounded-lg border-2 border-line-strong text-xl"
            aria-label="Меньше баллов"
            @click="setPoints(-1)"
          >
            −
          </button>
          <span
            class="min-w-8 text-center text-lg font-bold"
            aria-live="polite"
            >{{ draft.points }}</span
          >
          <button
            type="button"
            class="flex h-11 w-11 items-center justify-center rounded-lg border-2 border-line-strong text-xl"
            aria-label="Больше баллов"
            @click="setPoints(1)"
          >
            +
          </button>
        </span>
        <span
          v-if="
            type === 'gaps' ||
            type === 'match' ||
            type === 'order' ||
            type === 'multi'
          "
          class="text-sm text-ink-3"
        >
          делятся поровну, частично верный ответ даёт часть баллов
        </span>
      </template>
    </div>
  </div>
</template>
