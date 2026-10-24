<script setup lang="ts">
import { computed, defineAsyncComponent } from "vue";

import GlossaryTooltip from "@/components/shared/GlossaryTooltip.vue";
import { parseGlossary } from "@/utils/glossary";
import { splitInlineMath } from "@/utils/inlineMath";

/**
 * Renders legacy plain text that may carry `[Термин|Объяснение]` markup and
 * `$...$` inline formulas (see utils/inlineMath.ts). Rich (TipTap JSON)
 * bodies go through RichContent instead -- see `utils/richContent.ts` for
 * how the two are told apart.
 */
const props = defineProps<{ text: string }>();

// KaTeX is loaded only when a formula actually appears.
const MathView = defineAsyncComponent(() => import("@/components/richtext/MathView.vue"));

const segments = computed(() =>
  parseGlossary(props.text).flatMap((segment) =>
    segment.type === "text" ? splitInlineMath(segment.value) : [segment],
  ),
);
</script>

<template>
  <span>
    <template v-for="(segment, i) in segments" :key="i">
      <template v-if="segment.type === 'text'">{{ segment.value }}</template>
      <MathView v-else-if="segment.type === 'math'" :latex="segment.value" />
      <GlossaryTooltip v-else :term="segment.term" :explanation="segment.explanation" />
    </template>
  </span>
</template>
