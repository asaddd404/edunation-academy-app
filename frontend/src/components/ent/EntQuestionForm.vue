<script setup lang="ts">
import { computed } from "vue";

import BaseButton from "@/components/ui/BaseButton.vue";
import BaseInput from "@/components/ui/BaseInput.vue";
import type { EntQuestionType } from "@/types";
import { isQuestionFormValid, type QuestionForm } from "@/utils/entQuestionForm";
import { EXAM_LANGUAGES, LANGUAGE_LABEL } from "@/utils/examLanguage";

const props = defineProps<{
  form: QuestionForm;
  mode: "create" | "edit";
  /** Existing server-side image, shown only while `form.hasImage` is true. */
  imageUrl?: string | null;
  /** Bumped by the parent to force a fresh (cleared) file input. */
  fileInputKey: number;
}>();

const emit = defineEmits<{
  save: [];
  cancel: [];
  imagePicked: [file: File | null];
  removeImage: [];
}>();

const QTYPE_LABEL: Record<EntQuestionType, string> = {
  single: "Один правильный ответ",
  multiple: "Несколько правильных ответов",
  matching: "Сопоставление",
  short_answer: "Краткий ответ",
};

const isValid = computed(() => isQuestionFormValid(props.form));

function onQtypeChange() {
  const form = props.form;
  if (form.qtype === "multiple" || form.qtype === "matching") {
    form.maxScore = 2;
  } else if (form.maxScore === 2 && form.qtype !== "single" && form.qtype !== "short_answer") {
    form.maxScore = 1;
  }
}

function addChoice() {
  if (props.form.choices.length < 8) props.form.choices.push({ text: "", isCorrect: false });
}

function addMatchPair() {
  props.form.matchPairs.push({ promptText: "", answerText: "" });
}

function addAnswerVariant() {
  props.form.answerVariants.push("");
}

function onImagePicked(event: Event) {
  const input = event.target as HTMLInputElement;
  emit("imagePicked", input.files?.[0] ?? null);
}
</script>

<template>
  <div class="min-w-0 space-y-3">
    <p class="text-sm font-medium text-ink">
      {{ mode === "edit" ? "Редактирование вопроса" : "Новый вопрос" }}
    </p>

    <label class="block text-sm">
      <span class="mb-1.5 block font-medium text-ink-2">Тип вопроса</span>
      <select v-model="form.qtype" class="input min-h-11" @change="onQtypeChange">
        <option v-for="(label, value) in QTYPE_LABEL" :key="value" :value="value">{{ label }}</option>
      </select>
    </label>

    <label class="block text-sm">
      <span class="mb-1.5 block font-medium text-ink-2">Язык вопроса</span>
      <select v-model="form.language" class="input min-h-11">
        <option v-for="language in EXAM_LANGUAGES" :key="language" :value="language">
          {{ LANGUAGE_LABEL[language] }}
        </option>
      </select>
    </label>

    <BaseInput v-model="form.text" label="Текст вопроса" />

    <div class="text-sm">
      <span class="mb-1.5 block font-medium text-ink-2">Изображение к вопросу (необязательно)</span>
      <div class="flex flex-wrap items-center gap-3">
        <img
          v-if="form.hasImage && imageUrl"
          :src="imageUrl"
          alt=""
          class="h-20 w-28 rounded-lg border border-line object-cover"
        />
        <input
          :key="fileInputKey"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          class="text-sm text-ink-2 file:mr-3 file:rounded-lg file:border-0 file:bg-paper-2 file:px-3 file:py-2 file:text-sm file:text-ink hover:file:bg-line"
          @change="onImagePicked"
        />
        <BaseButton v-if="form.imageFile || form.hasImage" variant="secondary" @click="emit('removeImage')">
          Убрать изображение
        </BaseButton>
      </div>
      <p v-if="form.imageFile" class="mt-1.5 text-xs text-ink-3">
        Выбрано: {{ form.imageFile?.name }} — загрузится при сохранении вопроса.
      </p>
      <p class="mt-1.5 text-xs text-ink-3">jpg, png или webp, до 5 МБ.</p>
    </div>

    <label class="block text-sm" v-if="form.qtype !== 'multiple' && form.qtype !== 'matching'">
      <span class="mb-1.5 block font-medium text-ink-2">Баллы за вопрос</span>
      <select v-model.number="form.maxScore" class="input min-h-11">
        <option :value="1">1</option>
        <option :value="2">2 (профильный)</option>
      </select>
    </label>
    <p v-else class="text-sm text-ink-2">Баллы: 2 (2 — всё верно, 1 — частично, 0 — иначе)</p>

    <template v-if="form.qtype === 'single' || form.qtype === 'multiple'">
      <div v-for="(choice, i) in form.choices" :key="i" class="flex items-center gap-2">
        <input
          v-if="form.qtype === 'single'"
          type="radio"
          class="accent-moss"
          :name="`correct-${mode}`"
          :checked="choice.isCorrect"
          @change="form.choices.forEach((c, ci) => (c.isCorrect = ci === i))"
        />
        <input v-else type="checkbox" class="accent-moss" v-model="choice.isCorrect" />
        <input v-model="choice.text" placeholder="Вариант ответа" class="input min-h-11 flex-1" />
      </div>
      <BaseButton variant="secondary" @click="addChoice">+ вариант</BaseButton>
    </template>

    <template v-else-if="form.qtype === 'matching'">
      <div v-for="(pair, i) in form.matchPairs" :key="i" class="flex items-center gap-2">
        <input v-model="pair.promptText" placeholder="Слева (вопрос)" class="input min-h-11 flex-1" />
        <input v-model="pair.answerText" placeholder="Справа (правильная пара)" class="input min-h-11 flex-1" />
      </div>
      <BaseButton variant="secondary" @click="addMatchPair">+ пара</BaseButton>
    </template>

    <template v-else>
      <div v-for="(_, i) in form.answerVariants" :key="i" class="flex items-center gap-2">
        <input v-model="form.answerVariants[i]" placeholder="Принимаемый ответ" class="input min-h-11 flex-1" />
      </div>
      <BaseButton variant="secondary" @click="addAnswerVariant">+ вариант написания</BaseButton>
    </template>

    <div class="flex gap-2">
      <BaseButton :disabled="!isValid" @click="emit('save')">
        {{ mode === "edit" ? "Сохранить изменения" : "Сохранить вопрос" }}
      </BaseButton>
      <BaseButton v-if="mode === 'edit'" variant="secondary" @click="emit('cancel')">Отмена</BaseButton>
    </div>
  </div>
</template>
