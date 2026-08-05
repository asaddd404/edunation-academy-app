<script setup lang="ts">
import { reactive, ref } from "vue";
import { onMounted } from "vue";

import { createQuestion, listLessonQuestions } from "@/api/lessons";
import { deleteQuestion, updateQuestion } from "@/api/questions";
import { createSectionQuestion, listSectionQuestions } from "@/api/sections";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import BaseInput from "@/components/ui/BaseInput.vue";
import type { QuestionSavePayload, QuestionTeacher, QuestionType } from "@/types";

const props = defineProps<{ lessonId?: number; sectionId?: number }>();

const QTYPE_LABEL: Record<QuestionType, string> = {
  single: "Один правильный ответ",
  multiple: "Несколько правильных ответов",
  matching: "Сопоставление",
  short_answer: "Краткий ответ",
};

interface QuestionForm {
  qtype: QuestionType;
  text: string;
  maxScore: number;
  choices: { text: string; isCorrect: boolean }[];
  matchPairs: { promptText: string; answerText: string }[];
  answerVariants: string[];
}

function blankForm(): QuestionForm {
  return {
    qtype: "single",
    text: "",
    maxScore: 1,
    choices: [
      { text: "", isCorrect: true },
      { text: "", isCorrect: false },
    ],
    matchPairs: [
      { promptText: "", answerText: "" },
      { promptText: "", answerText: "" },
    ],
    answerVariants: [""],
  };
}

const questions = ref<QuestionTeacher[]>([]);
const loading = ref(true);
const formOpen = ref(false);
const editingId = ref<number | null>(null);
const form = reactive<QuestionForm>(blankForm());

async function load() {
  loading.value = true;
  questions.value = props.lessonId
    ? await listLessonQuestions(props.lessonId)
    : await listSectionQuestions(props.sectionId!);
  loading.value = false;
}

onMounted(load);

function openCreateForm() {
  Object.assign(form, blankForm());
  editingId.value = null;
  formOpen.value = true;
}

function startEdit(question: QuestionTeacher) {
  const fallback = blankForm();
  Object.assign(form, {
    qtype: question.qtype,
    text: question.text,
    maxScore: question.max_score,
    choices: question.choices.length
      ? question.choices.map((c) => ({ text: c.text, isCorrect: c.is_correct }))
      : fallback.choices,
    matchPairs: question.match_pairs.length
      ? question.match_pairs.map((p) => ({ promptText: p.prompt_text, answerText: p.answer_text }))
      : fallback.matchPairs,
    answerVariants: question.answer_variants.length ? question.answer_variants.map((v) => v.text) : [""],
  });
  editingId.value = question.id;
  formOpen.value = true;
}

function cancelForm() {
  formOpen.value = false;
  editingId.value = null;
}

function onQtypeChange() {
  if (form.qtype === "multiple" || form.qtype === "matching") {
    form.maxScore = 2;
  } else if (form.maxScore === 2) {
    form.maxScore = 1;
  }
}

function addChoice() {
  if (form.choices.length < 8) form.choices.push({ text: "", isCorrect: false });
}

function addMatchPair() {
  form.matchPairs.push({ promptText: "", answerText: "" });
}

function addAnswerVariant() {
  form.answerVariants.push("");
}

function isFormValid(): boolean {
  if (!form.text.trim()) return false;
  if (form.qtype === "single") {
    return (
      form.choices.length >= 2 &&
      form.choices.every((c) => c.text.trim()) &&
      form.choices.filter((c) => c.isCorrect).length === 1
    );
  }
  if (form.qtype === "multiple") {
    return (
      form.choices.length >= 2 &&
      form.choices.every((c) => c.text.trim()) &&
      form.choices.filter((c) => c.isCorrect).length >= 2
    );
  }
  if (form.qtype === "matching") {
    return form.matchPairs.length >= 2 && form.matchPairs.every((p) => p.promptText.trim() && p.answerText.trim());
  }
  return form.answerVariants.some((v) => v.trim());
}

async function handleSave() {
  if (!isFormValid()) return;

  const payload: QuestionSavePayload = {
    qtype: form.qtype,
    text: form.text,
    max_score: form.maxScore,
    choices:
      form.qtype === "single" || form.qtype === "multiple"
        ? form.choices.map((c) => ({ text: c.text, is_correct: c.isCorrect }))
        : undefined,
    match_pairs:
      form.qtype === "matching"
        ? form.matchPairs.map((p) => ({ prompt_text: p.promptText, answer_text: p.answerText }))
        : undefined,
    answer_variants: form.qtype === "short_answer" ? form.answerVariants.filter((v) => v.trim()) : undefined,
  };

  if (editingId.value !== null) {
    await updateQuestion(editingId.value, payload);
  } else if (props.lessonId) {
    await createQuestion(props.lessonId, payload);
  } else {
    await createSectionQuestion(props.sectionId!, payload);
  }

  formOpen.value = false;
  editingId.value = null;
  await load();
}

async function handleDelete(questionId: number) {
  if (!confirm("Удалить вопрос? Это действие необратимо.")) return;
  await deleteQuestion(questionId);
  await load();
}
</script>

<template>
  <div>
    <p v-if="loading" class="text-sm text-fg/60">Загрузка вопросов…</p>
    <ul v-else class="mb-3 space-y-2">
      <li
        v-for="q in questions"
        :key="q.id"
        class="flex items-start justify-between gap-3 rounded-lg border border-fg/10 p-3 text-sm"
      >
        <div>
          <BaseBadge tone="neutral">{{ QTYPE_LABEL[q.qtype] }}</BaseBadge>
          <BaseBadge tone="neutral">{{ q.max_score }} балл(а)</BaseBadge>
          <p class="mt-1">{{ q.text }}</p>
        </div>
        <div class="flex shrink-0 gap-2">
          <BaseButton variant="secondary" @click="startEdit(q)">Редактировать</BaseButton>
          <BaseButton variant="danger" @click="handleDelete(q.id)">Удалить</BaseButton>
        </div>
      </li>
      <li v-if="!questions.length" class="text-sm text-fg/60">Вопросов пока нет.</li>
    </ul>

    <BaseButton v-if="!formOpen" variant="secondary" @click="openCreateForm">Добавить вопрос</BaseButton>

    <div v-else class="space-y-3 rounded-lg bg-fg/5 p-4">
      <p class="text-sm font-medium">{{ editingId !== null ? "Редактирование вопроса" : "Новый вопрос" }}</p>

      <label class="block text-sm">
        <span class="mb-1.5 block font-medium text-fg/80">Тип вопроса</span>
        <select
          v-model="form.qtype"
          class="w-full rounded-lg border border-border bg-card px-4 py-2.5 text-sm text-fg"
          @change="onQtypeChange"
        >
          <option v-for="(label, value) in QTYPE_LABEL" :key="value" :value="value">{{ label }}</option>
        </select>
      </label>

      <BaseInput v-model="form.text" label="Текст вопроса" />

      <label class="block text-sm" v-if="form.qtype !== 'multiple' && form.qtype !== 'matching'">
        <span class="mb-1.5 block font-medium text-fg/80">Баллы за вопрос</span>
        <select v-model.number="form.maxScore" class="w-full rounded-lg border border-border bg-card px-4 py-2.5 text-sm text-fg">
          <option :value="1">1</option>
          <option :value="2">2 (профильный)</option>
        </select>
      </label>
      <p v-else class="text-sm text-fg/60">Баллы: 2 (2 — всё верно, 1 — частично, 0 — иначе)</p>

      <template v-if="form.qtype === 'single' || form.qtype === 'multiple'">
        <div v-for="(choice, i) in form.choices" :key="i" class="flex items-center gap-2">
          <input
            v-if="form.qtype === 'single'"
            type="radio"
            name="correct-choice"
            :checked="choice.isCorrect"
            @change="form.choices.forEach((c, ci) => (c.isCorrect = ci === i))"
          />
          <input v-else type="checkbox" v-model="choice.isCorrect" />
          <input
            v-model="choice.text"
            placeholder="Вариант ответа"
            class="flex-1 rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm"
          />
        </div>
        <BaseButton variant="secondary" @click="addChoice">+ вариант</BaseButton>
      </template>

      <template v-else-if="form.qtype === 'matching'">
        <div v-for="(pair, i) in form.matchPairs" :key="i" class="flex items-center gap-2">
          <input
            v-model="pair.promptText"
            placeholder="Слева (вопрос)"
            class="flex-1 rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm"
          />
          <input
            v-model="pair.answerText"
            placeholder="Справа (правильная пара)"
            class="flex-1 rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm"
          />
        </div>
        <BaseButton variant="secondary" @click="addMatchPair">+ пара</BaseButton>
      </template>

      <template v-else>
        <div v-for="(_, i) in form.answerVariants" :key="i" class="flex items-center gap-2">
          <input
            v-model="form.answerVariants[i]"
            placeholder="Принимаемый ответ"
            class="flex-1 rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm"
          />
        </div>
        <BaseButton variant="secondary" @click="addAnswerVariant">+ вариант написания</BaseButton>
      </template>

      <div class="flex gap-2">
        <BaseButton :disabled="!isFormValid()" @click="handleSave">
          {{ editingId !== null ? "Сохранить изменения" : "Сохранить вопрос" }}
        </BaseButton>
        <BaseButton variant="secondary" @click="cancelForm">Отмена</BaseButton>
      </div>
    </div>
  </div>
</template>
