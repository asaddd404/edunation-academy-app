<script setup lang="ts">
import { isAxiosError } from "axios";
import { ArrowRight, Check, Pencil, Plus, Trash2 } from "@lucide/vue";
import { onMounted, ref } from "vue";

import { createQuestion, listLessonQuestions } from "@/api/lessons";
import { deleteQuestion, updateQuestion } from "@/api/questions";
import { createSectionQuestion, listSectionQuestions } from "@/api/sections";
import QuestionEditor from "@/components/course/QuestionEditor.vue";
import SmartText from "@/components/shared/SmartText.vue";
import BaseBadge from "@/components/ui/BaseBadge.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { QuestionSavePayload, QuestionTeacher } from "@/types";
import { optionLetter } from "@/utils/examOptions";
import { QTYPE_LABEL } from "@/utils/questionForm";

/** The questions of one lesson mini-test or one section test: listed with
 * their answer key, edited in place, added at the bottom. */
const props = defineProps<{ lessonId?: number; sectionId?: number }>();

const questions = ref<QuestionTeacher[]>([]);
const loading = ref(true);
const loadError = ref("");

/** "new", a question id being edited, or null when the editor is closed. */
const editing = ref<"new" | number | null>(null);
const saving = ref(false);
const saveError = ref("");
const confirmingDelete = ref<number | null>(null);

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    questions.value = props.lessonId
      ? await listLessonQuestions(props.lessonId)
      : await listSectionQuestions(props.sectionId!);
  } catch {
    loadError.value = "Не удалось загрузить вопросы.";
  } finally {
    loading.value = false;
  }
}

onMounted(load);

function open(target: "new" | number) {
  editing.value = target;
  saveError.value = "";
  confirmingDelete.value = null;
}

/** FastAPI answers a refused body with either a sentence or a list of
 * field errors; either way the teacher gets words, not "422". */
function describeError(e: unknown): string {
  const detail = isAxiosError(e) ? e.response?.data?.detail : null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d: { msg?: string }) => (d.msg ?? "").replace(/^Value error, /, "")).join("; ");
  }
  return "Не удалось сохранить вопрос. Попробуйте ещё раз.";
}

async function save(payload: QuestionSavePayload) {
  saving.value = true;
  saveError.value = "";
  try {
    if (typeof editing.value === "number") {
      const updated = await updateQuestion(editing.value, payload);
      questions.value = questions.value.map((q) => (q.id === updated.id ? updated : q));
    } else {
      const created = props.lessonId
        ? await createQuestion(props.lessonId, payload)
        : await createSectionQuestion(props.sectionId!, payload);
      questions.value = [...questions.value, created];
    }
    editing.value = null;
  } catch (e) {
    saveError.value = describeError(e);
  } finally {
    saving.value = false;
  }
}

async function remove(questionId: number) {
  try {
    await deleteQuestion(questionId);
    questions.value = questions.value.filter((q) => q.id !== questionId);
  } catch {
    loadError.value = "Не удалось удалить вопрос.";
  } finally {
    confirmingDelete.value = null;
  }
}
</script>

<template>
  <div class="space-y-3">
    <div v-if="loading" class="space-y-2">
      <div v-for="i in 2" :key="i" class="h-20 animate-pulse rounded-xl bg-paper-2" />
    </div>
    <p v-else-if="loadError" class="text-sm text-clay">
      {{ loadError }} <button type="button" class="underline" @click="load">Повторить</button>
    </p>

    <ol v-else class="space-y-3">
      <li v-for="(q, index) in questions" :key="q.id">
        <QuestionEditor
          v-if="editing === q.id"
          :question="q"
          :saving="saving"
          :error="saveError"
          @save="save"
          @cancel="editing = null"
        />

        <article
          v-else
          class="group rounded-xl border border-line bg-paper p-3 transition-all duration-200 hover:border-moss/40 hover:shadow-sm sm:p-4"
        >
          <header class="flex flex-wrap items-start gap-2">
            <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-moss/10 text-xs font-semibold text-moss">
              {{ index + 1 }}
            </span>
            <div class="min-w-0 flex-1">
              <div class="mb-1 flex flex-wrap gap-1.5">
                <BaseBadge tone="neutral">{{ QTYPE_LABEL[q.qtype] }}</BaseBadge>
                <BaseBadge tone="neutral">{{ q.max_score }} балл(а)</BaseBadge>
              </div>
              <p class="text-sm font-medium text-ink"><SmartText :text="q.text" /></p>
            </div>
            <div class="flex shrink-0 gap-1">
              <button
                type="button"
                class="flex h-8 w-8 items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-paper-2 hover:text-ink"
                aria-label="Редактировать вопрос"
                @click="open(q.id)"
              >
                <Pencil :size="16" />
              </button>
              <button
                type="button"
                class="flex h-8 w-8 items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-clay/10 hover:text-clay"
                aria-label="Удалить вопрос"
                @click="confirmingDelete = q.id"
              >
                <Trash2 :size="16" />
              </button>
            </div>
          </header>

          <!-- The answer key at a glance, so a wrong key is spotted without opening the editor. -->
          <ul v-if="q.choices.length" class="mt-2 grid gap-1 pl-9 text-sm sm:grid-cols-2">
            <li
              v-for="(c, i) in q.choices"
              :key="c.id"
              class="flex items-center gap-2 rounded-lg px-2 py-1"
              :class="c.is_correct ? 'bg-moss/10 text-ink' : 'text-ink-2'"
            >
              <span class="w-4 shrink-0 text-xs font-semibold text-ink-3">{{ optionLetter(i) }}</span>
              <span class="min-w-0 flex-1 truncate">{{ c.text }}</span>
              <Check v-if="c.is_correct" :size="14" :stroke-width="3" class="shrink-0 text-moss" />
            </li>
          </ul>
          <ul v-else-if="q.match_pairs.length" class="mt-2 space-y-1 pl-9 text-sm text-ink-2">
            <li v-for="p in q.match_pairs" :key="p.id" class="flex items-center gap-2">
              <span class="min-w-0 truncate">{{ p.prompt_text }}</span>
              <ArrowRight :size="14" class="shrink-0 text-ink-3" />
              <span class="min-w-0 truncate font-medium text-ink">{{ p.answer_text }}</span>
            </li>
          </ul>
          <p v-else-if="q.answer_variants.length" class="mt-2 pl-9 text-sm text-ink-2">
            Принимается: <span class="font-medium text-ink">{{ q.answer_variants.map((v) => v.text).join(" / ") }}</span>
          </p>

          <div
            v-if="confirmingDelete === q.id"
            class="mt-3 flex flex-wrap items-center gap-2 rounded-lg bg-clay/10 p-2 text-sm text-clay"
            role="alert"
          >
            <span class="flex-1">Удалить вопрос? Отменить будет нельзя.</span>
            <BaseButton variant="danger" @click="remove(q.id)">Удалить</BaseButton>
            <BaseButton variant="secondary" @click="confirmingDelete = null">Отмена</BaseButton>
          </div>
        </article>
      </li>
      <li v-if="!questions.length && editing !== 'new'" class="rounded-xl border border-dashed border-line p-4 text-center text-sm text-ink-2">
        Вопросов пока нет — тест появится у учеников, как только вы добавите первый.
      </li>
    </ol>

    <QuestionEditor v-if="editing === 'new'" :saving="saving" :error="saveError" @save="save" @cancel="editing = null" />
    <button
      v-else-if="!loading && !loadError"
      type="button"
      class="flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-line py-3 text-sm font-medium text-ink-2 transition-colors hover:border-moss/50 hover:bg-moss/5 hover:text-moss"
      @click="open('new')"
    >
      <Plus :size="16" /> Добавить вопрос
    </button>
  </div>
</template>
