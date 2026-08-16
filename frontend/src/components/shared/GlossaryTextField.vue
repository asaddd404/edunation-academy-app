<script setup lang="ts">
import { Eye, EyeOff, Lightbulb, Pencil, Trash2 } from "@lucide/vue";
import { computed, ref } from "vue";

import SmartText from "@/components/shared/SmartText.vue";
import { extractGlossaryTerms } from "@/utils/glossary";
import type { GlossaryTermSegment } from "@/utils/glossary";

const props = withDefaults(defineProps<{ modelValue: string; label: string; rows?: number }>(), { rows: 3 });
const emit = defineEmits<{ (e: "update:modelValue", value: string): void }>();

const textarea = ref<HTMLTextAreaElement | null>(null);
const previewMode = ref(false);

const terms = computed(() => extractGlossaryTerms(props.modelValue));

// Popover state shared by both "add a new hint" (selection-driven) and
// "edit an existing chip's explanation" (term-driven, no selection needed).
const popover = ref<{ mode: "add"; start: number; end: number; selected: string } | { mode: "edit"; term: string } | null>(
  null,
);
const explanationDraft = ref("");

function openAddPopover() {
  const el = textarea.value;
  if (!el) return;
  const start = el.selectionStart;
  const end = el.selectionEnd;
  if (start === end) return; // nothing selected -- nothing to wrap
  popover.value = { mode: "add", start, end, selected: props.modelValue.slice(start, end) };
  explanationDraft.value = "";
}

function openEditPopover(segment: GlossaryTermSegment) {
  popover.value = { mode: "edit", term: segment.term };
  explanationDraft.value = segment.explanation;
}

function closePopover() {
  popover.value = null;
  explanationDraft.value = "";
}

function confirmPopover() {
  if (!popover.value || !explanationDraft.value.trim()) return;
  const explanation = explanationDraft.value.trim();

  if (popover.value.mode === "add") {
    const { start, end, selected } = popover.value;
    const next = `${props.modelValue.slice(0, start)}[${selected}|${explanation}]${props.modelValue.slice(end)}`;
    emit("update:modelValue", next);
  } else {
    const { term } = popover.value;
    const existing = terms.value.find((t) => t.term === term);
    if (existing) {
      const marker = `[${existing.term}|${existing.explanation}]`;
      emit("update:modelValue", props.modelValue.replace(marker, `[${term}|${explanation}]`));
    }
  }
  closePopover();
}

function removeTerm(segment: GlossaryTermSegment) {
  const marker = `[${segment.term}|${segment.explanation}]`;
  emit("update:modelValue", props.modelValue.replace(marker, segment.term));
}
</script>

<template>
  <div>
    <div class="mb-1.5 flex items-center justify-between">
      <span class="text-label text-ink-2">{{ label }}</span>
      <div class="flex items-center gap-1">
        <button
          type="button"
          class="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-ink-2 transition-colors hover:bg-paper-2 hover:text-ink"
          title="Выделите текст в поле, затем нажмите, чтобы добавить подсказку"
          @click="openAddPopover"
        >
          <Lightbulb :size="14" :stroke-width="1.8" />
          Добавить подсказку
        </button>
        <button
          type="button"
          class="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-ink-2 transition-colors hover:bg-paper-2 hover:text-ink"
          @click="previewMode = !previewMode"
        >
          <EyeOff v-if="previewMode" :size="14" :stroke-width="1.8" />
          <Eye v-else :size="14" :stroke-width="1.8" />
          {{ previewMode ? "Редактирование" : "Предпросмотр" }}
        </button>
      </div>
    </div>

    <textarea
      v-if="!previewMode"
      ref="textarea"
      :value="modelValue"
      :rows="rows"
      class="input"
      @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
    />
    <div v-else class="input min-h-[3rem] whitespace-pre-line">
      <SmartText :text="modelValue" />
    </div>

    <div v-if="terms.length" class="mt-2 flex flex-wrap gap-1.5">
      <span
        v-for="segment in terms"
        :key="segment.term"
        class="inline-flex items-center gap-1 rounded-full bg-moss/10 py-1 pl-2.5 pr-1.5 text-xs font-medium text-moss"
      >
        {{ segment.term }}
        <button type="button" class="rounded p-0.5 hover:bg-moss/20" title="Редактировать" @click="openEditPopover(segment)">
          <Pencil :size="11" :stroke-width="2" />
        </button>
        <button type="button" class="rounded p-0.5 hover:bg-moss/20" title="Удалить подсказку" @click="removeTerm(segment)">
          <Trash2 :size="11" :stroke-width="2" />
        </button>
      </span>
    </div>

    <div v-if="popover" class="mt-2 space-y-2 rounded-lg border border-line bg-paper-2 p-3">
      <p class="text-xs text-ink-2">
        Термин: <span class="font-medium text-ink">{{ popover.mode === "add" ? popover.selected : popover.term }}</span>
      </p>
      <textarea
        v-model="explanationDraft"
        rows="2"
        placeholder="Понятное объяснение…"
        class="input text-sm"
        autofocus
      />
      <div class="flex gap-2">
        <button
          type="button"
          class="btn-primary px-3 py-1.5 text-xs"
          :disabled="!explanationDraft.trim()"
          @click="confirmPopover"
        >
          Сохранить
        </button>
        <button type="button" class="btn-ghost px-3 py-1.5 text-xs" @click="closePopover">Отмена</button>
      </div>
    </div>
  </div>
</template>
