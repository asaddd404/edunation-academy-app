<script setup lang="ts">
import { CircleAlert, CircleCheck } from "@lucide/vue";
import { computed } from "vue";

import type { EntQuestionType, EntSubjectStructure, ExamLanguage } from "@/types";
import { EXAM_LANGUAGES } from "@/utils/examLanguage";

/**
 * What a simulation of the subject is made of, block by block, against what
 * the bank holds in each language -- so a teacher sees at a glance what is
 * missing ("КЗ: на основе текста 3 из 5") instead of finding out when a
 * student cannot start a test. A row click filters the question list to
 * that type; a second click clears it.
 */
const props = defineProps<{ structure: EntSubjectStructure; activeQtype: EntQuestionType | null }>();
const emit = defineEmits<{ select: [qtype: EntQuestionType | null] }>();

const LANG: Record<ExamLanguage, string> = { ru: "RU", kk: "KZ" };

const LABEL: Record<EntQuestionType, { title: string; profileHint: string; hint: string }> = {
  single: { title: "Один правильный ответ", profileHint: "4 варианта · 1 балл", hint: "один верный вариант" },
  context: { title: "На основе текста", profileHint: "текст + 4 варианта · 1 балл", hint: "текст + один верный вариант" },
  matching: { title: "Сопоставление", profileHint: "можно с лишними вариантами · 2 балла", hint: "2 балла" },
  multiple: { title: "Несколько правильных", profileHint: "1–3 верных из 6 · 2 балла", hint: "1–3 верных · 2 балла" },
  short_answer: { title: "Краткий ответ", profileHint: "", hint: "ответ вводится текстом" },
};

const totalNeeded = computed(() => props.structure.blocks.reduce((sum, b) => sum + b.needed, 0));

function ready(language: ExamLanguage): boolean {
  return props.structure.blocks.every((b) => b.have[language] >= b.needed);
}

function toggle(qtype: EntQuestionType) {
  emit("select", props.activeQtype === qtype ? null : qtype);
}
</script>

<template>
  <section class="card p-4 sm:p-5" aria-labelledby="structure-title">
    <div class="flex flex-wrap items-baseline justify-between gap-2">
      <h3 id="structure-title" class="font-medium text-ink">
        <template v-if="structure.is_profile">Структура теста: 40 вопросов, 50 баллов</template>
        <template v-else-if="totalNeeded">Структура теста: {{ totalNeeded }} вопросов по квотам</template>
        <template v-else>Вопросы в банке по типам</template>
      </h3>
      <div class="flex gap-2 text-xs">
        <span
          v-for="language in EXAM_LANGUAGES"
          :key="language"
          class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-medium"
          :class="ready(language) ? 'bg-moss/15 text-moss' : 'bg-clay/15 text-clay'"
        >
          <CircleCheck v-if="ready(language)" :size="12" />
          <CircleAlert v-else :size="12" />
          {{ LANG[language] }}: {{ ready(language) ? "тест собирается" : "не хватает вопросов" }}
        </span>
      </div>
    </div>

    <div class="mt-3 overflow-hidden rounded-xl border border-line">
      <div class="grid grid-cols-[1fr_auto_auto] gap-x-3 bg-paper-2 px-3 py-2 text-xs font-medium text-ink-3 sm:grid-cols-[4.5rem_1fr_6rem_6rem]">
        <span class="hidden sm:block">№</span>
        <span>Тип вопроса</span>
        <span v-for="language in EXAM_LANGUAGES" :key="language" class="w-20 text-right sm:w-auto">{{ LANG[language] }}</span>
      </div>
      <button
        v-for="block in structure.blocks"
        :key="block.qtype"
        type="button"
        class="grid w-full grid-cols-[1fr_auto_auto] items-center gap-x-3 border-t border-line px-3 py-2.5 text-left text-sm transition-colors sm:grid-cols-[4.5rem_1fr_6rem_6rem]"
        :class="activeQtype === block.qtype ? 'bg-moss/10' : 'hover:bg-paper-2'"
        :aria-pressed="activeQtype === block.qtype"
        :title="activeQtype === block.qtype ? 'Показать все вопросы' : 'Показать только вопросы этого типа'"
        @click="toggle(block.qtype)"
      >
        <span class="hidden font-medium text-ink-2 sm:block">
          {{ block.first_number ? `${block.first_number}–${block.last_number}` : "—" }}
        </span>
        <span class="min-w-0">
          <span class="block font-medium text-ink">
            <span v-if="block.first_number" class="text-ink-3 sm:hidden">{{ block.first_number }}–{{ block.last_number }} · </span>
            {{ LABEL[block.qtype].title }}
          </span>
          <span class="block text-xs text-ink-3">
            {{ structure.is_profile ? LABEL[block.qtype].profileHint : LABEL[block.qtype].hint }}
            <template v-if="!structure.is_profile"> · в тест: {{ block.needed || "не берётся" }}</template>
          </span>
          <span
            v-if="EXAM_LANGUAGES.some((l) => block.off_format[l] > 0)"
            class="block text-xs text-clay"
          >
            Не по формату (не попадут в тест):
            {{ EXAM_LANGUAGES.filter((l) => block.off_format[l] > 0).map((l) => `${LANG[l]} ${block.off_format[l]}`).join(", ") }}
          </span>
        </span>
        <span
          v-for="language in EXAM_LANGUAGES"
          :key="language"
          class="w-20 text-right tabular-nums sm:w-auto"
          :class="block.have[language] >= block.needed ? 'text-ink' : 'font-semibold text-clay'"
        >
          {{ block.have[language] }}<span v-if="block.needed" class="text-ink-3"> / {{ block.needed }}</span>
          <span v-if="block.have[language] < block.needed" class="block text-[11px] font-normal">
            ещё {{ block.needed - block.have[language] }}
          </span>
        </span>
      </button>
    </div>

    <p v-if="EXAM_LANGUAGES.some((l) => structure.unused[l] > 0)" class="mt-2 text-xs text-ink-3">
      Вопросы типов, которых нет в структуре, в тест не попадают:
      {{ EXAM_LANGUAGES.map((l) => `${LANG[l]} ${structure.unused[l]}`).join(", ") }}.
    </p>
    <p class="mt-2 text-xs text-ink-3">Нажмите на строку, чтобы показать в списке только вопросы этого типа.</p>
  </section>
</template>
