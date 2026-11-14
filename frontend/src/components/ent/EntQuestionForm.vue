<script setup lang="ts">
import { X } from "@lucide/vue";
import { computed } from "vue";

import GlossaryTextField from "@/components/shared/GlossaryTextField.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import FilePicker from "@/components/ui/FilePicker.vue";
import type { EntQuestionType } from "@/types";
import {
  adaptToQtype,
  MAX_MATCH_ROWS,
  profileOptionCount,
  questionFormProblem,
  type QuestionForm,
} from "@/utils/entQuestionForm";
import { EXAM_LANGUAGES, LANGUAGE_LABEL } from "@/utils/examLanguage";
import { pluralRu } from "@/utils/subjectTheme";

const props = defineProps<{
  form: QuestionForm;
  mode: "create" | "edit";
  /** The subject is a profile one: the fixed ЕНТ format (4 / 6 options, no short answer). */
  profile?: boolean;
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
  context: "Задание на основе текста",
  multiple: "Несколько правильных ответов",
  matching: "Сопоставление",
  short_answer: "Краткий ответ",
};

const qtypeOptions = computed(() =>
  (Object.keys(QTYPE_LABEL) as EntQuestionType[]).filter((qtype) => !(props.profile && qtype === "short_answer")),
);

const problem = computed(() => questionFormProblem(props.form, props.profile));
const hasChoices = computed(() => ["single", "context", "multiple"].includes(props.form.qtype));
const isSingleAnswer = computed(() => props.form.qtype === "single" || props.form.qtype === "context");
// In a profile subject the option count is the format's, not the teacher's.
const fixedOptionCount = computed(() => (props.profile ? profileOptionCount(props.form.qtype) : null));
const maxOptions = computed(() => (isSingleAnswer.value ? 6 : 8));
const matchRows = computed(() => props.form.matchPairs.length + props.form.matchDistractors.length);

function onQtypeChange() {
  adaptToQtype(props.form, !!props.profile);
}

function addChoice() {
  if (props.form.choices.length < maxOptions.value) props.form.choices.push({ text: "", isCorrect: false });
}

function removeChoice(index: number) {
  props.form.choices.splice(index, 1);
  if (isSingleAnswer.value && !props.form.choices.some((c) => c.isCorrect) && props.form.choices.length) {
    props.form.choices[0].isCorrect = true;
  }
}

function addMatchPair() {
  if (matchRows.value < MAX_MATCH_ROWS) props.form.matchPairs.push({ promptText: "", answerText: "" });
}

function addDistractor() {
  if (matchRows.value < MAX_MATCH_ROWS) props.form.matchDistractors.push("");
}

function addAnswerVariant() {
  props.form.answerVariants.push("");
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
        <option v-for="value in qtypeOptions" :key="value" :value="value">{{ QTYPE_LABEL[value] }}</option>
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

    <label v-if="form.qtype === 'context'" class="block text-sm">
      <span class="mb-1.5 block font-medium text-ink-2">Текст (контекст), на основе которого задан вопрос</span>
      <textarea
        v-model="form.contextText"
        rows="6"
        maxlength="5000"
        placeholder="Отрывок, условие или описание ситуации…"
        class="input resize-y"
      />
    </label>

    <GlossaryTextField v-model="form.text" label="Текст вопроса" />

    <div class="text-sm">
      <span class="mb-1.5 block font-medium text-ink-2">Изображение к вопросу (необязательно)</span>
      <div class="flex flex-wrap items-center gap-3">
        <img
          v-if="form.hasImage && imageUrl"
          :src="imageUrl"
          alt=""
          class="h-20 w-28 rounded-lg border border-line object-cover"
        />
        <FilePicker
          :file="form.imageFile ?? null"
          accept="image/jpeg,image/png,image/webp"
          :label="form.hasImage ? 'Заменить изображение' : 'Выбрать изображение'"
          @pick="emit('imagePicked', $event)"
          @clear="emit('imagePicked', null)"
        />
        <BaseButton v-if="form.imageFile || form.hasImage" variant="secondary" @click="emit('removeImage')">
          Убрать изображение
        </BaseButton>
      </div>
      <p v-if="form.imageFile" class="mt-1.5 text-xs text-ink-3">
        Загрузится при сохранении вопроса.
      </p>
      <p class="mt-1.5 text-xs text-ink-3">jpg, png или webp, до 5 МБ.</p>
    </div>

    <p v-if="form.qtype === 'multiple' || form.qtype === 'matching'" class="text-sm text-ink-2">
      Баллы: 2 (2 — всё верно, 1 — частично, 0 — иначе)
    </p>
    <p v-else-if="profile" class="text-sm text-ink-2">Баллы: 1</p>
    <label v-else class="block text-sm">
      <span class="mb-1.5 block font-medium text-ink-2">Баллы за вопрос</span>
      <select v-model.number="form.maxScore" class="input min-h-11">
        <option :value="1">1</option>
        <option :value="2">2</option>
      </select>
    </label>

    <template v-if="hasChoices">
      <p class="text-xs text-ink-3">
        <template v-if="isSingleAnswer">Отметьте один правильный вариант</template>
        <template v-else>Отметьте от 1 до 3 правильных вариантов</template>
        <template v-if="fixedOptionCount"> · в профильном предмете ровно {{ fixedOptionCount }} вариантов</template>
      </p>
      <div v-for="(choice, i) in form.choices" :key="i" class="flex items-center gap-2">
        <input
          v-if="isSingleAnswer"
          type="radio"
          class="accent-moss"
          :name="`correct-${mode}`"
          :checked="choice.isCorrect"
          :aria-label="`Вариант ${i + 1} правильный`"
          @change="form.choices.forEach((c, ci) => (c.isCorrect = ci === i))"
        />
        <input v-else v-model="choice.isCorrect" type="checkbox" class="accent-moss" :aria-label="`Вариант ${i + 1} правильный`" />
        <input v-model="choice.text" placeholder="Вариант ответа" class="input min-h-11 flex-1" />
        <button
          v-if="!fixedOptionCount && form.choices.length > 2"
          type="button"
          class="rounded-lg p-2 text-ink-3 hover:bg-paper-2 hover:text-clay"
          :aria-label="`Удалить вариант ${i + 1}`"
          @click="removeChoice(i)"
        >
          <X :size="16" />
        </button>
      </div>
      <BaseButton v-if="!fixedOptionCount && form.choices.length < maxOptions" variant="secondary" @click="addChoice">
        + вариант
      </BaseButton>
    </template>

    <template v-else-if="form.qtype === 'matching'">
      <p class="text-xs text-ink-3">
        Пары: слева — вопрос, справа — правильный ответ. Лишние варианты ответа показываются ученику справа вместе с
        правильными, но ни к чему не подходят.
      </p>
      <div v-for="(pair, i) in form.matchPairs" :key="`p${i}`" class="flex items-center gap-2">
        <input v-model="pair.promptText" placeholder="Слева (вопрос)" class="input min-h-11 min-w-0 flex-1" />
        <input v-model="pair.answerText" placeholder="Справа (правильная пара)" class="input min-h-11 min-w-0 flex-1" />
        <button
          v-if="form.matchPairs.length > 2"
          type="button"
          class="rounded-lg p-2 text-ink-3 hover:bg-paper-2 hover:text-clay"
          :aria-label="`Удалить пару ${i + 1}`"
          @click="form.matchPairs.splice(i, 1)"
        >
          <X :size="16" />
        </button>
      </div>
      <div v-for="(_, i) in form.matchDistractors" :key="`d${i}`" class="flex items-center gap-2">
        <span class="flex min-h-11 min-w-0 flex-1 items-center rounded-lg border border-dashed border-line px-3 text-xs text-ink-3">
          лишний вариант — без пары
        </span>
        <input v-model="form.matchDistractors[i]" placeholder="Справа (лишний ответ)" class="input min-h-11 min-w-0 flex-1" />
        <button
          type="button"
          class="rounded-lg p-2 text-ink-3 hover:bg-paper-2 hover:text-clay"
          :aria-label="`Удалить лишний вариант ${i + 1}`"
          @click="form.matchDistractors.splice(i, 1)"
        >
          <X :size="16" />
        </button>
      </div>
      <div class="flex flex-wrap gap-2">
        <BaseButton variant="secondary" :disabled="matchRows >= MAX_MATCH_ROWS" @click="addMatchPair">+ пара</BaseButton>
        <BaseButton variant="secondary" :disabled="matchRows >= MAX_MATCH_ROWS" @click="addDistractor">
          + лишний вариант ответа
        </BaseButton>
      </div>
      <p class="text-xs text-ink-3">
        Ученик увидит {{ form.matchPairs.length }}
        {{ pluralRu(form.matchPairs.length, ["вопрос", "вопроса", "вопросов"]) }} слева и {{ matchRows }}
        {{ pluralRu(matchRows, ["вариант", "варианта", "вариантов"]) }} ответа справа.
      </p>
    </template>

    <template v-else>
      <div v-for="(_, i) in form.answerVariants" :key="i" class="flex items-center gap-2">
        <input v-model="form.answerVariants[i]" placeholder="Принимаемый ответ" class="input min-h-11 flex-1" />
      </div>
      <BaseButton variant="secondary" @click="addAnswerVariant">+ вариант написания</BaseButton>
    </template>

    <p v-if="problem && form.text.trim()" class="text-xs text-clay">{{ problem }}</p>

    <div class="flex gap-2">
      <BaseButton :disabled="!!problem" @click="emit('save')">
        {{ mode === "edit" ? "Сохранить изменения" : "Сохранить вопрос" }}
      </BaseButton>
      <BaseButton v-if="mode === 'edit'" variant="secondary" @click="emit('cancel')">Отмена</BaseButton>
    </div>
  </div>
</template>
