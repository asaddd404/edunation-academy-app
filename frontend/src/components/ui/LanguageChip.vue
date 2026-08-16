<script setup lang="ts">
import type { ExamLanguage } from "@/types";
import { LANGUAGE_LABEL } from "@/utils/examLanguage";

/**
 * The exam language as a two-letter plate rather than a flag emoji.
 *
 * Windows does not render regional-indicator pairs as flags at all -- it
 * shows the bare letters "RU"/"KZ" in the system font -- so the emoji was
 * never actually a flag for this app's users. Drawing the plate ourselves
 * makes it look deliberate and keeps it on the theme palette.
 */
withDefaults(defineProps<{ language: ExamLanguage; size?: "sm" | "md" }>(), { size: "sm" });

const CODE: Record<ExamLanguage, string> = { ru: "RU", kk: "KZ" };
</script>

<template>
  <span
    class="inline-flex shrink-0 items-center justify-center rounded-md border border-line-strong bg-paper-2 font-semibold tracking-wide text-ink-2"
    :class="size === 'md' ? 'h-7 px-2 text-xs' : 'h-5 px-1.5 text-[10px]'"
    :title="LANGUAGE_LABEL[language]"
  >
    {{ CODE[language] }}
  </span>
</template>
