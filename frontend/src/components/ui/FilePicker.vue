<script setup lang="ts">
import { Paperclip, X } from "@lucide/vue";

/**
 * A file field that looks like the rest of the app. The browser's own
 * control renders "Choose File / No file chosen" in the OS language, in the
 * OS style, and cannot be restyled -- so it is hidden and driven by a label.
 * The parent owns the chosen file; this only reports picks and clears.
 */
withDefaults(
  defineProps<{
    file: File | null;
    accept?: string;
    label?: string;
    disabled?: boolean;
  }>(),
  { accept: undefined, label: "Прикрепить файл", disabled: false },
);

const emit = defineEmits<{ pick: [file: File]; clear: [] }>();

function onChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const picked = input.files?.[0];
  // Cleared right away so picking the same file again still fires `change`.
  input.value = "";
  if (picked) emit("pick", picked);
}
</script>

<template>
  <div class="flex min-w-0 flex-wrap items-center gap-2">
    <label
      class="inline-flex min-h-10 cursor-pointer items-center gap-1.5 rounded-lg border border-line-strong bg-paper px-3 text-sm font-medium text-ink-2 transition-colors hover:border-moss/50 hover:text-ink focus-within:ring-2 focus-within:ring-moss/40"
      :class="disabled ? 'pointer-events-none opacity-50' : ''"
    >
      <Paperclip :size="15" :stroke-width="1.8" />
      {{ file ? "Заменить файл" : label }}
      <input type="file" class="sr-only" :accept="accept" :disabled="disabled" @change="onChange" />
    </label>
    <span
      v-if="file"
      class="inline-flex min-w-0 max-w-full items-center gap-1 rounded-full bg-moss/10 py-1 pl-3 pr-1 text-xs text-ink"
    >
      <span class="truncate">{{ file.name }}</span>
      <button
        type="button"
        class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-ink-3 hover:bg-moss/20 hover:text-ink"
        :aria-label="`Убрать файл ${file.name}`"
        @click="emit('clear')"
      >
        <X :size="12" />
      </button>
    </span>
  </div>
</template>
