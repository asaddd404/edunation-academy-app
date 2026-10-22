<script setup lang="ts">
import type { AnswerPayload, RenderableQuestion } from "@/types";
import { optionLetter } from "@/utils/examOptions";

/**
 * The answer controls for all four question types -- single, multiple,
 * matching and short answer -- shared by lesson tests, section tests and the
 * ЕНТ simulator. The question text (and an ЕНТ image) stay with the caller,
 * which lays them out differently on each screen.
 *
 * Works as `v-model`: the parent owns the answer, this only emits the next
 * one. For matching, the value sent for a prompt is the answer's opaque
 * token exactly as the server handed it out.
 */
const props = defineProps<{
  question: RenderableQuestion;
  modelValue?: AnswerPayload;
  disabled?: boolean;
}>();

const emit = defineEmits<{ "update:modelValue": [answer: AnswerPayload] }>();

function selectSingle(choiceId: number) {
  emit("update:modelValue", { question_id: props.question.id, choice_id: choiceId });
}

function toggleMultiple(choiceId: number, checked: boolean) {
  const current = props.modelValue?.choice_ids ?? [];
  const next = checked ? [...current.filter((id) => id !== choiceId), choiceId] : current.filter((id) => id !== choiceId);
  emit("update:modelValue", { question_id: props.question.id, choice_ids: next });
}

function setPair(promptId: number, answerToken: string) {
  emit("update:modelValue", {
    question_id: props.question.id,
    pairs: { ...(props.modelValue?.pairs ?? {}), [String(promptId)]: answerToken },
  });
}

function setText(text: string) {
  emit("update:modelValue", { question_id: props.question.id, text });
}

const isSelected = (choiceId: number) => props.modelValue?.choice_id === choiceId;
const isChecked = (choiceId: number) => (props.modelValue?.choice_ids ?? []).includes(choiceId);
const pairFor = (promptId: number) => props.modelValue?.pairs?.[String(promptId)] ?? "";
</script>

<template>
  <div class="space-y-2" :class="disabled ? 'pointer-events-none opacity-70' : ''">
    <template v-if="question.qtype === 'single'">
      <label
        v-for="(choice, i) in question.choices"
        :key="choice.id"
        class="group/opt flex cursor-pointer items-center gap-3 rounded-xl border px-3.5 py-3 text-sm text-ink transition-all duration-150"
        :class="isSelected(choice.id) ? 'border-moss bg-moss/10 shadow-sm' : 'border-line hover:border-moss/50 hover:bg-paper-2'"
      >
        <!-- The native control stays in the DOM (keyboard, screen readers,
             form semantics) but the lettered badge is what the student
             actually sees and clicks. -->
        <input
          type="radio"
          class="sr-only"
          :name="`q-${question.id}`"
          :value="choice.id"
          :checked="isSelected(choice.id)"
          :disabled="disabled"
          @change="selectSingle(choice.id)"
        />
        <span
          class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sm font-semibold transition-colors duration-150"
          :class="isSelected(choice.id) ? 'bg-moss text-moss-fg' : 'bg-paper-2 text-ink-2 group-hover/opt:bg-line'"
        >
          {{ optionLetter(i) }}
        </span>
        <span class="flex-1">{{ choice.text }}</span>
      </label>
    </template>

    <template v-else-if="question.qtype === 'multiple'">
      <p class="text-xs text-ink-3">Выберите все верные варианты</p>
      <label
        v-for="(choice, i) in question.choices"
        :key="choice.id"
        class="group/opt flex cursor-pointer items-center gap-3 rounded-xl border px-3.5 py-3 text-sm text-ink transition-all duration-150"
        :class="isChecked(choice.id) ? 'border-moss bg-moss/10 shadow-sm' : 'border-line hover:border-moss/50 hover:bg-paper-2'"
      >
        <input
          type="checkbox"
          class="sr-only"
          :checked="isChecked(choice.id)"
          :disabled="disabled"
          @change="toggleMultiple(choice.id, ($event.target as HTMLInputElement).checked)"
        />
        <!-- Square badge, unlike the single-choice one, so "выберите
             несколько" is readable from the shape alone. -->
        <span
          class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border-2 text-sm font-semibold transition-colors duration-150"
          :class="
            isChecked(choice.id)
              ? 'border-moss bg-moss text-moss-fg'
              : 'border-line-strong bg-paper text-ink-2 group-hover/opt:border-moss/50'
          "
        >
          {{ optionLetter(i) }}
        </span>
        <span class="flex-1">{{ choice.text }}</span>
      </label>
    </template>

    <template v-else-if="question.qtype === 'matching'">
      <div
        v-for="(prompt, i) in question.match_prompts"
        :key="prompt.id"
        class="flex flex-col gap-2 rounded-xl border px-3.5 py-3 text-sm transition-colors duration-150 sm:flex-row sm:items-center"
        :class="pairFor(prompt.id) ? 'border-moss/50 bg-moss/5' : 'border-line'"
      >
        <span class="flex flex-1 items-center gap-3">
          <span
            class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sm font-semibold transition-colors duration-150"
            :class="pairFor(prompt.id) ? 'bg-moss text-moss-fg' : 'bg-paper-2 text-ink-2'"
          >
            {{ optionLetter(i) }}
          </span>
          <span class="text-ink">{{ prompt.text }}</span>
        </span>
        <select
          class="input sm:w-1/2"
          :value="pairFor(prompt.id)"
          :disabled="disabled"
          @change="setPair(prompt.id, ($event.target as HTMLSelectElement).value)"
        >
          <option value="" disabled>Выберите пару</option>
          <option v-for="opt in question.match_answers" :key="opt.id" :value="opt.id">{{ opt.text }}</option>
        </select>
      </div>
    </template>

    <template v-else>
      <input
        type="text"
        placeholder="Ваш ответ"
        class="input"
        :value="modelValue?.text ?? ''"
        :disabled="disabled"
        @input="setText(($event.target as HTMLInputElement).value)"
      />
    </template>
  </div>
</template>
