<script setup lang="ts">
import { reactive, ref } from "vue";
import { onMounted } from "vue";

import {
  createEntSubject,
  createSubjectQuestion,
  deleteEntQuestion,
  listSubjectQuestions,
  listTeacherEntSubjects,
  updateEntSubject,
  updateSubjectQuestion,
} from "@/api/ent";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import BaseInput from "@/components/ui/BaseInput.vue";
import type { EntQuestionTeacher, EntQuestionType, EntSubject } from "@/types";

const QTYPE_LABEL: Record<EntQuestionType, string> = {
  single: "Один правильный ответ",
  multiple: "Несколько правильных ответов",
  matching: "Сопоставление",
  short_answer: "Краткий ответ",
};

const subjects = ref<EntSubject[]>([]);
const loading = ref(true);
const newSubjectName = ref("");

const openSubjectId = ref<number | null>(null);
const questionsBySubject = reactive<Record<number, EntQuestionTeacher[]>>({});
const questionsLoading = ref(false);
const editingQuestionId = ref<number | null>(null);

const renamingSubjectId = ref<number | null>(null);
const renameValue = ref("");

interface QuestionForm {
  qtype: EntQuestionType;
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

const questionForms = reactive<Record<number, QuestionForm>>({});

async function load() {
  loading.value = true;
  subjects.value = await listTeacherEntSubjects();
  loading.value = false;
}

onMounted(load);

async function handleCreateSubject() {
  if (!newSubjectName.value.trim()) return;
  const subject = await createEntSubject({ name: newSubjectName.value });
  newSubjectName.value = "";
  await load();
  // Jump straight to the question form for the subject just created,
  // instead of leaving the teacher to figure out that clicking its
  // name is what reveals it.
  openSubjectId.value = subject.id;
  editingQuestionId.value = null;
  if (!questionForms[subject.id]) questionForms[subject.id] = blankForm();
  questionsBySubject[subject.id] = await listSubjectQuestions(subject.id);
}

async function handleToggleActive(subject: EntSubject) {
  await updateEntSubject(subject.id, { is_active: !subject.is_active });
  await load();
}

function startRenameSubject(subject: EntSubject) {
  renamingSubjectId.value = subject.id;
  renameValue.value = subject.name;
}

function cancelRenameSubject() {
  renamingSubjectId.value = null;
}

async function handleRenameSubject(subjectId: number) {
  if (!renameValue.value.trim()) return;
  await updateEntSubject(subjectId, { name: renameValue.value.trim() });
  renamingSubjectId.value = null;
  await load();
}

async function toggleSubject(subjectId: number) {
  if (openSubjectId.value === subjectId) {
    openSubjectId.value = null;
    return;
  }
  openSubjectId.value = subjectId;
  editingQuestionId.value = null;
  if (!questionForms[subjectId]) questionForms[subjectId] = blankForm();
  if (!questionsBySubject[subjectId]) {
    questionsLoading.value = true;
    questionsBySubject[subjectId] = await listSubjectQuestions(subjectId);
    questionsLoading.value = false;
  }
}

function startEditQuestion(subjectId: number, question: EntQuestionTeacher) {
  editingQuestionId.value = question.id;
  const fallback = blankForm();
  questionForms[subjectId] = {
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
  };
}

function cancelEditQuestion(subjectId: number) {
  editingQuestionId.value = null;
  questionForms[subjectId] = blankForm();
}

function onQtypeChange(subjectId: number) {
  const form = questionForms[subjectId];
  if (form.qtype === "multiple" || form.qtype === "matching") {
    form.maxScore = 2;
  } else if (form.maxScore === 2 && form.qtype !== "single" && form.qtype !== "short_answer") {
    form.maxScore = 1;
  }
}

function addChoice(subjectId: number) {
  const form = questionForms[subjectId];
  if (form.choices.length < 8) form.choices.push({ text: "", isCorrect: false });
}

function addMatchPair(subjectId: number) {
  questionForms[subjectId].matchPairs.push({ promptText: "", answerText: "" });
}

function addAnswerVariant(subjectId: number) {
  questionForms[subjectId].answerVariants.push("");
}

function isFormValid(form: QuestionForm): boolean {
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

async function handleSaveQuestion(subjectId: number) {
  const form = questionForms[subjectId];
  if (!isFormValid(form)) return;

  const payload = {
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
    answer_variants:
      form.qtype === "short_answer" ? form.answerVariants.filter((v) => v.trim()) : undefined,
  };

  if (editingQuestionId.value !== null) {
    await updateSubjectQuestion(editingQuestionId.value, payload);
  } else {
    await createSubjectQuestion(subjectId, payload);
  }

  editingQuestionId.value = null;
  questionForms[subjectId] = blankForm();
  questionsBySubject[subjectId] = await listSubjectQuestions(subjectId);
  await load();
}

async function handleDeleteQuestion(subjectId: number, questionId: number) {
  await deleteEntQuestion(questionId);
  questionsBySubject[subjectId] = questionsBySubject[subjectId].filter((q) => q.id !== questionId);
  if (editingQuestionId.value === questionId) cancelEditQuestion(subjectId);
  await load();
}
</script>

<template>
  <div>
    <h1 class="mb-2 text-2xl font-semibold">Банк вопросов ЕНТ-симулятора</h1>
    <p class="mb-6 text-sm text-fg/60">
      Сначала добавьте предмет, затем откройте его карточку кнопкой «Вопросы» — там же добавляются и редактируются
      вопросы всех типов (один/несколько ответов, сопоставление, короткий ответ).
    </p>

    <form
      class="mb-6 flex flex-col gap-3 rounded-xl border border-fg/10 p-4 sm:flex-row sm:items-end"
      @submit.prevent="handleCreateSubject"
    >
      <BaseInput v-model="newSubjectName" label="Новый предмет" class="flex-1" />
      <BaseButton type="submit">Добавить предмет</BaseButton>
    </form>

    <p v-if="loading" class="text-fg/60">Загрузка…</p>

    <div v-else class="space-y-4">
      <div v-for="subject in subjects" :key="subject.id" class="rounded-xl border border-fg/10 p-4">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="flex flex-1 items-center gap-2">
            <template v-if="renamingSubjectId === subject.id">
              <input
                v-model="renameValue"
                class="rounded-lg border border-fg/20 bg-transparent px-2 py-1 text-lg font-medium"
                @keyup.enter="handleRenameSubject(subject.id)"
                @keyup.escape="cancelRenameSubject"
              />
              <BaseButton @click="handleRenameSubject(subject.id)">Сохранить</BaseButton>
              <BaseButton variant="secondary" @click="cancelRenameSubject">Отмена</BaseButton>
            </template>
            <template v-else>
              <span class="text-lg font-medium">{{ subject.name }}</span>
              <button class="text-sm text-fg/50 hover:text-fg" @click="startRenameSubject(subject)">
                Переименовать
              </button>
              <BaseBadge tone="neutral">{{ subject.question_count }} вопросов</BaseBadge>
              <BaseBadge :tone="subject.is_active ? 'success' : 'warning'">
                {{ subject.is_active ? "активен" : "скрыт" }}
              </BaseBadge>
            </template>
          </div>
          <BaseButton variant="secondary" @click="toggleSubject(subject.id)">
            {{ openSubjectId === subject.id ? "Свернуть" : "Вопросы" }}
          </BaseButton>
          <BaseButton variant="secondary" @click="handleToggleActive(subject)">
            {{ subject.is_active ? "Скрыть" : "Показать" }}
          </BaseButton>
        </div>

        <div v-if="openSubjectId === subject.id" class="mt-4 space-y-4 border-t border-fg/10 pt-4">
          <p v-if="questionsLoading" class="text-sm text-fg/60">Загрузка вопросов…</p>
          <ul v-else class="space-y-2">
            <li
              v-for="q in questionsBySubject[subject.id]"
              :key="q.id"
              class="flex items-start justify-between gap-3 rounded-lg border border-fg/10 p-3 text-sm"
            >
              <div>
                <BaseBadge tone="neutral">{{ QTYPE_LABEL[q.qtype] }}</BaseBadge>
                <BaseBadge tone="neutral">{{ q.max_score }} балл(а)</BaseBadge>
                <p class="mt-1">{{ q.text }}</p>
              </div>
              <div class="flex shrink-0 gap-2">
                <BaseButton variant="secondary" @click="startEditQuestion(subject.id, q)">Редактировать</BaseButton>
                <BaseButton variant="danger" @click="handleDeleteQuestion(subject.id, q.id)">Удалить</BaseButton>
              </div>
            </li>
            <li v-if="!questionsBySubject[subject.id]?.length" class="text-sm text-fg/60">Вопросов пока нет.</li>
          </ul>

          <div class="space-y-3 rounded-lg bg-fg/5 p-4">
            <p class="text-sm font-medium">
              {{ editingQuestionId !== null ? "Редактирование вопроса" : "Новый вопрос" }}
            </p>

            <label class="block text-sm">
              <span class="mb-1.5 block font-medium text-fg/80">Тип вопроса</span>
              <select
                v-model="questionForms[subject.id].qtype"
                class="w-full rounded-lg border border-fg/20 bg-transparent px-4 py-2.5 text-sm"
                @change="onQtypeChange(subject.id)"
              >
                <option v-for="(label, value) in QTYPE_LABEL" :key="value" :value="value">{{ label }}</option>
              </select>
            </label>

            <BaseInput v-model="questionForms[subject.id].text" label="Текст вопроса" />

            <label class="block text-sm" v-if="questionForms[subject.id].qtype !== 'multiple' && questionForms[subject.id].qtype !== 'matching'">
              <span class="mb-1.5 block font-medium text-fg/80">Баллы за вопрос</span>
              <select
                v-model.number="questionForms[subject.id].maxScore"
                class="w-full rounded-lg border border-fg/20 bg-transparent px-4 py-2.5 text-sm"
              >
                <option :value="1">1</option>
                <option :value="2">2 (профильный)</option>
              </select>
            </label>
            <p v-else class="text-sm text-fg/60">Баллы: 2 (2 — всё верно, 1 — частично, 0 — иначе)</p>

            <template v-if="questionForms[subject.id].qtype === 'single' || questionForms[subject.id].qtype === 'multiple'">
              <div v-for="(choice, i) in questionForms[subject.id].choices" :key="i" class="flex items-center gap-2">
                <input
                  v-if="questionForms[subject.id].qtype === 'single'"
                  type="radio"
                  :name="`correct-${subject.id}`"
                  :checked="choice.isCorrect"
                  @change="questionForms[subject.id].choices.forEach((c, ci) => (c.isCorrect = ci === i))"
                />
                <input v-else type="checkbox" v-model="choice.isCorrect" />
                <input
                  v-model="choice.text"
                  placeholder="Вариант ответа"
                  class="flex-1 rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm"
                />
              </div>
              <BaseButton variant="secondary" @click="addChoice(subject.id)">+ вариант</BaseButton>
            </template>

            <template v-else-if="questionForms[subject.id].qtype === 'matching'">
              <div v-for="(pair, i) in questionForms[subject.id].matchPairs" :key="i" class="flex items-center gap-2">
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
              <BaseButton variant="secondary" @click="addMatchPair(subject.id)">+ пара</BaseButton>
            </template>

            <template v-else>
              <div v-for="(_, i) in questionForms[subject.id].answerVariants" :key="i" class="flex items-center gap-2">
                <input
                  v-model="questionForms[subject.id].answerVariants[i]"
                  placeholder="Принимаемый ответ"
                  class="flex-1 rounded-lg border border-fg/20 bg-transparent px-3 py-2 text-sm"
                />
              </div>
              <BaseButton variant="secondary" @click="addAnswerVariant(subject.id)">+ вариант написания</BaseButton>
            </template>

            <div class="flex gap-2">
              <BaseButton :disabled="!isFormValid(questionForms[subject.id])" @click="handleSaveQuestion(subject.id)">
                {{ editingQuestionId !== null ? "Сохранить изменения" : "Сохранить вопрос" }}
              </BaseButton>
              <BaseButton v-if="editingQuestionId !== null" variant="secondary" @click="cancelEditQuestion(subject.id)">
                Отмена
              </BaseButton>
            </div>
          </div>
        </div>
      </div>
      <p v-if="!subjects.length" class="text-fg/60">Пока нет ни одного предмета.</p>
    </div>
  </div>
</template>
