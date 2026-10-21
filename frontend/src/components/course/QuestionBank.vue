<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { onMounted } from "vue";

import { createQuestion, listLessonQuestions, updateLesson } from "@/api/lessons";
import { deleteQuestion, updateQuestion } from "@/api/questions";
import { createSectionQuestion, listSectionQuestions, updateSection } from "@/api/sections";
import GlossaryTextField from "@/components/shared/GlossaryTextField.vue";
import SmartText from "@/components/shared/SmartText.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { QuestionSavePayload, QuestionTeacher, QuestionType } from "@/types";

const props = defineProps<{ lessonId?: number; sectionId?: number; perAttempt?: number | null }>();
const emit = defineEmits<{ (e: "update:perAttempt", value: number | null): void }>();

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

// How many questions one attempt draws from this bank. 0 in the input = all.
// With a bank larger than that, every attempt a student starts gets a
// different selection -- the backend avoids the previous attempt's questions.
const perAttemptInput = ref<number>(props.perAttempt ?? 0);
const perAttemptSaving = ref(false);
const perAttemptSaved = ref(false);
const perAttemptError = ref("");

const effectivePerAttempt = computed(() =>
  perAttemptInput.value > 0 ? Math.min(perAttemptInput.value, questions.value.length) : questions.value.length,
);

async function savePerAttempt() {
  const value = Math.max(0, Math.min(100, Math.floor(Number(perAttemptInput.value) || 0)));
  perAttemptInput.value = value;
  if (value === (props.perAttempt ?? 0)) return;
  perAttemptSaving.value = true;
  perAttemptSaved.value = false;
  perAttemptError.value = "";
  try {
    if (props.lessonId) await updateLesson(props.lessonId, { questions_per_attempt: value });
    else await updateSection(props.sectionId!, { questions_per_attempt: value });
    emit("update:perAttempt", value || null);
    perAttemptSaved.value = true;
  } catch {
    perAttemptError.value = "Не удалось сохранить настройку.";
  } finally {
    perAttemptSaving.value = false;
  }
}

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
    <div v-if="loading" class="mb-3 space-y-2">
      <div class="h-14 animate-pulse rounded-lg bg-paper-2" />
      <div class="h-14 animate-pulse rounded-lg bg-paper-2" />
    </div>
    <ul v-else class="mb-3 space-y-2">
      <li
        v-for="q in questions"
        :key="q.id"
        class="flex flex-col gap-3 rounded-lg border border-line p-3 text-sm sm:flex-row sm:items-start sm:justify-between"
      >
        <div class="min-w-0">
          <BaseBadge tone="neutral">{{ QTYPE_LABEL[q.qtype] }}</BaseBadge>
          <BaseBadge tone="neutral">{{ q.max_score }} балл(а)</BaseBadge>
          <p class="mt-1 text-ink"><SmartText :text="q.text" /></p>
        </div>
        <div class="flex shrink-0 flex-wrap gap-2">
          <BaseButton variant="secondary" @click="startEdit(q)">Редактировать</BaseButton>
          <BaseButton variant="danger" @click="handleDelete(q.id)">Удалить</BaseButton>
        </div>
      </li>
      <li v-if="!questions.length" class="text-sm text-ink-2">Вопросов пока нет.</li>
    </ul>

    <div v-if="!loading && questions.length" class="mb-3 space-y-1.5 rounded-lg bg-paper-2 p-3 text-sm">
      <label class="flex flex-wrap items-center gap-2 text-ink">
        Вопросов в одной попытке:
        <input
          v-model.number="perAttemptInput"
          type="number"
          min="0"
          max="100"
          class="input w-20 py-1"
          :disabled="perAttemptSaving"
          @change="savePerAttempt"
        />
        <span class="text-ink-3">(0 — все)</span>
        <span v-if="perAttemptSaved" class="text-moss">Сохранено</span>
      </label>
      <p v-if="perAttemptError" class="text-clay">{{ perAttemptError }}</p>
      <p v-else-if="effectivePerAttempt < questions.length" class="text-ink-3">
        В банке {{ questions.length }}, ученик получает {{ effectivePerAttempt }} случайных — каждая новая попытка
        будет с другими вопросами.
      </p>
      <p v-else class="text-ink-3">
        Каждая попытка показывает все {{ questions.length }} вопр. в новом порядке. Чтобы попытки отличались вопросами,
        добавьте в банк больше вопросов, чем в попытке.
      </p>
    </div>

    <BaseButton v-if="!formOpen" variant="secondary" @click="openCreateForm">Добавить вопрос</BaseButton>

    <div v-else class="space-y-3 rounded-lg bg-paper-2 p-4">
      <p class="text-sm font-medium text-ink">{{ editingId !== null ? "Редактирование вопроса" : "Новый вопрос" }}</p>

      <label class="block text-sm">
        <span class="mb-1.5 block font-medium text-ink-2">Тип вопроса</span>
        <select v-model="form.qtype" class="input" @change="onQtypeChange">
          <option v-for="(label, value) in QTYPE_LABEL" :key="value" :value="value">{{ label }}</option>
        </select>
      </label>

      <GlossaryTextField v-model="form.text" label="Текст вопроса" />

      <label class="block text-sm" v-if="form.qtype !== 'multiple' && form.qtype !== 'matching'">
        <span class="mb-1.5 block font-medium text-ink-2">Баллы за вопрос</span>
        <select v-model.number="form.maxScore" class="input">
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
            name="correct-choice"
            :checked="choice.isCorrect"
            @change="form.choices.forEach((c, ci) => (c.isCorrect = ci === i))"
          />
          <input v-else type="checkbox" v-model="choice.isCorrect" />
          <input v-model="choice.text" placeholder="Вариант ответа" class="input flex-1" />
        </div>
        <BaseButton variant="secondary" @click="addChoice">+ вариант</BaseButton>
      </template>

      <template v-else-if="form.qtype === 'matching'">
        <div v-for="(pair, i) in form.matchPairs" :key="i" class="flex items-center gap-2">
          <input v-model="pair.promptText" placeholder="Слева (вопрос)" class="input flex-1" />
          <input v-model="pair.answerText" placeholder="Справа (правильная пара)" class="input flex-1" />
        </div>
        <BaseButton variant="secondary" @click="addMatchPair">+ пара</BaseButton>
      </template>

      <template v-else>
        <div v-for="(_, i) in form.answerVariants" :key="i" class="flex items-center gap-2">
          <input v-model="form.answerVariants[i]" placeholder="Принимаемый ответ" class="input flex-1" />
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
