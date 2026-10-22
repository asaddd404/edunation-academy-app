<script setup lang="ts">
import { ArrowLeftRight, ArrowRight, Check, CircleDot, Eye, ListChecks, Plus, TextCursorInput, Trash2 } from "@lucide/vue";
import { computed, reactive, ref, watch } from "vue";

import GlossaryTextField from "@/components/shared/GlossaryTextField.vue";
import SmartText from "@/components/shared/SmartText.vue";
import QuestionRenderer from "@/components/test/QuestionRenderer.vue";
import BaseButton from "@/components/ui/BaseButton.vue";
import type { AnswerPayload, QuestionSavePayload, QuestionTeacher, QuestionType } from "@/types";
import { optionLetter } from "@/utils/examOptions";
import {
  LIMITS,
  QTYPE_HINT,
  QTYPE_LABEL,
  blankForm,
  choiceRow,
  formFromQuestion,
  pairRow,
  setQtype,
  toPayload,
  toPreview,
  validate,
  variantRow,
} from "@/utils/questionForm";
import { pluralRu } from "@/utils/subjectTheme";

/**
 * Builds or edits one lesson/section test question, beside a live preview
 * of exactly what a student will be shown -- rendered by the same
 * QuestionRenderer the test itself uses, so the two cannot drift apart.
 */
const props = defineProps<{
  question?: QuestionTeacher | null;
  saving?: boolean;
  /** A refusal from the server, shown under the form. */
  error?: string;
}>();

const emit = defineEmits<{ save: [payload: QuestionSavePayload]; cancel: [] }>();

const form = reactive(props.question ? formFromQuestion(props.question) : blankForm());
watch(
  () => props.question,
  (q) => Object.assign(form, q ? formFromQuestion(q) : blankForm()),
);

const TYPES: { value: QuestionType; icon: typeof CircleDot }[] = [
  { value: "single", icon: CircleDot },
  { value: "multiple", icon: ListChecks },
  { value: "matching", icon: ArrowLeftRight },
  { value: "short_answer", icon: TextCursorInput },
];

const problems = computed(() => validate(form));
// Problems are listed only once the teacher has tried to save -- a blank
// form is not an error, and a wall of red before the first keystroke is noise.
const attempted = ref(false);

const choiceBounds = computed(() => (form.qtype === "single" ? LIMITS.singleChoices : LIMITS.multipleChoices));

function toggleCorrect(index: number) {
  if (form.qtype === "single") form.choices.forEach((c, i) => (c.isCorrect = i === index));
  else form.choices[index].isCorrect = !form.choices[index].isCorrect;
}

function removeChoice(index: number) {
  const wasCorrect = form.choices[index].isCorrect;
  form.choices.splice(index, 1);
  // A single-choice question must keep a correct answer to stay valid.
  if (form.qtype === "single" && wasCorrect && form.choices.length) form.choices[0].isCorrect = true;
}

function submit() {
  attempted.value = true;
  if (problems.value.length) return;
  emit("save", toPayload(form));
}

// Preview state: the teacher can click through it like a student would.
const preview = computed(() => toPreview(form));
const previewAnswer = ref<AnswerPayload | undefined>();
const showKey = ref(false);
watch(() => form.qtype, () => (previewAnswer.value = undefined));
</script>

<template>
  <div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
    <!-- ── Editor ─────────────────────────────────────────────────────── -->
    <form class="space-y-5 rounded-2xl border border-line bg-paper p-4 sm:p-5" novalidate @submit.prevent="submit">
      <p class="text-sm font-semibold text-ink">{{ question ? "Редактирование вопроса" : "Новый вопрос" }}</p>

      <fieldset>
        <legend class="mb-2 text-label text-ink-2">Тип вопроса</legend>
        <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <button
            v-for="t in TYPES"
            :key="t.value"
            type="button"
            class="flex flex-col items-start gap-1 rounded-xl border p-3 text-left transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-moss/50"
            :class="
              form.qtype === t.value
                ? 'border-moss bg-moss/10 shadow-sm'
                : 'border-line hover:-translate-y-px hover:border-moss/40 hover:bg-paper-2'
            "
            :aria-pressed="form.qtype === t.value"
            @click="setQtype(form, t.value)"
          >
            <component :is="t.icon" :size="18" :stroke-width="1.8" :class="form.qtype === t.value ? 'text-moss' : 'text-ink-3'" />
            <span class="text-sm font-medium text-ink">{{ QTYPE_LABEL[t.value] }}</span>
            <span class="text-[11px] leading-snug text-ink-3">{{ QTYPE_HINT[t.value] }}</span>
          </button>
        </div>
      </fieldset>

      <div>
        <GlossaryTextField v-model="form.text" label="Текст вопроса" />
        <p class="mt-1 text-right text-[11px] tabular-nums" :class="form.text.length > LIMITS.text ? 'text-clay' : 'text-ink-3'">
          {{ form.text.length }} / {{ LIMITS.text }}
        </p>
      </div>

      <div v-if="form.qtype === 'single' || form.qtype === 'short_answer'" class="flex flex-wrap items-center gap-3">
        <span class="text-label text-ink-2">Баллы</span>
        <div class="inline-flex rounded-lg border border-line bg-paper-2 p-0.5">
          <button
            v-for="score in [1, 2]"
            :key="score"
            type="button"
            class="rounded-md px-3 py-1 text-sm font-medium transition-colors"
            :class="form.maxScore === score ? 'bg-paper text-ink shadow-sm' : 'text-ink-2 hover:text-ink'"
            :aria-pressed="form.maxScore === score"
            @click="form.maxScore = score"
          >
            {{ score === 1 ? "1" : "2 · профильный" }}
          </button>
        </div>
      </div>
      <p v-else class="text-xs text-ink-3">2 балла: всё верно — 2, частично — 1, иначе — 0.</p>

      <!-- Choices -->
      <div v-if="form.qtype === 'single' || form.qtype === 'multiple'" class="space-y-2">
        <p class="text-label text-ink-2">
          Варианты · {{ form.qtype === "single" ? "нажмите на кружок у верного" : "отметьте все верные" }}
        </p>
        <TransitionGroup tag="ul" class="space-y-2" move-class="transition-transform duration-200" leave-active-class="hidden">
          <li v-for="(choice, i) in form.choices" :key="choice.key" class="flex items-center gap-2">
            <button
              type="button"
              class="flex h-9 w-9 shrink-0 items-center justify-center border-2 transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-moss/50"
              :class="[
                form.qtype === 'single' ? 'rounded-full' : 'rounded-lg',
                choice.isCorrect ? 'border-moss bg-moss text-moss-fg' : 'border-line-strong text-transparent hover:border-moss/60',
              ]"
              :aria-pressed="choice.isCorrect"
              :aria-label="`Вариант ${optionLetter(i)} — ${choice.isCorrect ? 'верный' : 'неверный'}`"
              @click="toggleCorrect(i)"
            >
              <Check :size="16" :stroke-width="3" />
            </button>
            <span class="w-5 shrink-0 text-center text-sm font-semibold text-ink-3">{{ optionLetter(i) }}</span>
            <input
              v-model="choice.text"
              :maxlength="LIMITS.choice"
              class="input min-w-0 flex-1"
              :class="choice.isCorrect ? 'border-moss/50' : ''"
              :placeholder="`Вариант ${optionLetter(i)}`"
            />
            <button
              type="button"
              class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-clay/10 hover:text-clay disabled:pointer-events-none disabled:opacity-30"
              :disabled="form.choices.length <= choiceBounds.min"
              :aria-label="`Удалить вариант ${optionLetter(i)}`"
              @click="removeChoice(i)"
            >
              <Trash2 :size="16" />
            </button>
          </li>
        </TransitionGroup>
        <button
          type="button"
          class="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium text-moss transition-colors hover:bg-moss/10 disabled:opacity-40"
          :disabled="form.choices.length >= choiceBounds.max"
          @click="form.choices.push(choiceRow())"
        >
          <Plus :size="16" /> Добавить вариант
        </button>
      </div>

      <!-- Matching -->
      <div v-else-if="form.qtype === 'matching'" class="space-y-2">
        <p class="text-label text-ink-2">Пары · ученик увидит правую колонку перемешанной</p>
        <ul class="space-y-2">
          <li v-for="(pair, i) in form.matchPairs" :key="pair.key" class="flex flex-col gap-2 rounded-xl border border-line p-2 sm:flex-row sm:items-center sm:border-0 sm:p-0">
            <input v-model="pair.promptText" :maxlength="LIMITS.pair" class="input min-w-0 flex-1" :placeholder="`Слева ${i + 1}`" />
            <ArrowRight :size="16" class="hidden shrink-0 text-ink-3 sm:block" />
            <div class="flex min-w-0 flex-1 items-center gap-2">
              <input v-model="pair.answerText" :maxlength="LIMITS.pair" class="input min-w-0 flex-1" placeholder="Верная пара справа" />
              <button
                type="button"
                class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-clay/10 hover:text-clay disabled:pointer-events-none disabled:opacity-30"
                :disabled="form.matchPairs.length <= LIMITS.pairs.min"
                :aria-label="`Удалить пару ${i + 1}`"
                @click="form.matchPairs.splice(i, 1)"
              >
                <Trash2 :size="16" />
              </button>
            </div>
          </li>
        </ul>
        <button
          type="button"
          class="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium text-moss transition-colors hover:bg-moss/10 disabled:opacity-40"
          :disabled="form.matchPairs.length >= LIMITS.pairs.max"
          @click="form.matchPairs.push(pairRow())"
        >
          <Plus :size="16" /> Добавить пару
        </button>
      </div>

      <!-- Short answer -->
      <div v-else class="space-y-2">
        <p class="text-label text-ink-2">Принимаемые ответы · регистр и лишние пробелы не учитываются</p>
        <ul class="space-y-2">
          <li v-for="(variant, i) in form.answerVariants" :key="variant.key" class="flex items-center gap-2">
            <input v-model="variant.text" :maxlength="LIMITS.variant" class="input min-w-0 flex-1" :placeholder="i ? 'Другое написание' : 'Верный ответ'" />
            <button
              type="button"
              class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-clay/10 hover:text-clay disabled:pointer-events-none disabled:opacity-30"
              :disabled="form.answerVariants.length <= 1"
              :aria-label="`Удалить ответ ${i + 1}`"
              @click="form.answerVariants.splice(i, 1)"
            >
              <Trash2 :size="16" />
            </button>
          </li>
        </ul>
        <button
          type="button"
          class="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-sm font-medium text-moss transition-colors hover:bg-moss/10"
          @click="form.answerVariants.push(variantRow())"
        >
          <Plus :size="16" /> Другое написание
        </button>
      </div>

      <ul v-if="attempted && problems.length" class="space-y-1 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-700 dark:text-red-400" role="alert">
        <li v-for="p in problems" :key="p">• {{ p }}</li>
      </ul>
      <p v-if="error" class="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-700 dark:text-red-400" role="alert">{{ error }}</p>

      <div class="flex flex-wrap items-center gap-2">
        <BaseButton type="submit" variant="cta" :disabled="saving">
          {{ saving ? "Сохранение…" : question ? "Сохранить изменения" : "Добавить вопрос" }}
        </BaseButton>
        <BaseButton variant="secondary" :disabled="saving" @click="emit('cancel')">Отмена</BaseButton>
        <span v-if="!problems.length" class="inline-flex items-center gap-1 text-xs text-moss">
          <Check :size="14" /> Готово к сохранению
        </span>
      </div>
    </form>

    <!-- ── Preview ────────────────────────────────────────────────────── -->
    <aside class="self-start rounded-2xl border border-dashed border-moss/40 bg-moss/[0.03] p-4 lg:sticky lg:top-24">
      <div class="mb-3 flex items-center justify-between gap-2">
        <p class="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-moss">
          <Eye :size="14" /> Так увидит ученик
        </p>
        <label class="inline-flex cursor-pointer items-center gap-1.5 text-xs text-ink-2">
          <input v-model="showKey" type="checkbox" class="accent-[rgb(var(--moss))]" />
          Ответ
        </label>
      </div>

      <p class="mb-3 text-body font-medium text-ink">
        <SmartText v-if="form.text.trim()" :text="form.text" />
        <span v-else class="text-ink-3">Текст вопроса…</span>
      </p>
      <QuestionRenderer v-model="previewAnswer" :question="preview" />

      <div v-if="showKey" class="mt-3 rounded-xl bg-paper-2 p-3 text-xs text-ink-2">
        <template v-if="form.qtype === 'single' || form.qtype === 'multiple'">
          Верно:
          <strong class="text-ink">
            {{ form.choices.map((c, i) => (c.isCorrect ? optionLetter(i) : "")).filter(Boolean).join(", ") || "—" }}
          </strong>
        </template>
        <ul v-else-if="form.qtype === 'matching'" class="space-y-0.5">
          <li v-for="p in form.matchPairs" :key="p.key">{{ p.promptText || "…" }} → <strong class="text-ink">{{ p.answerText || "…" }}</strong></li>
        </ul>
        <template v-else>
          Принимается:
          <strong class="text-ink">{{ form.answerVariants.map((v) => v.text.trim()).filter(Boolean).join(" / ") || "—" }}</strong>
        </template>
      </div>
      <p class="mt-3 text-[11px] text-ink-3">{{ form.maxScore }} {{ pluralRu(form.maxScore, ["балл", "балла", "баллов"]) }} · {{ QTYPE_LABEL[form.qtype] }}</p>
    </aside>
  </div>
</template>
