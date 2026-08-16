<script setup lang="ts">
import { computed } from "vue";

import GlossaryTooltip from "@/components/shared/GlossaryTooltip.vue";
import { parseGlossary } from "@/utils/glossary";

/**
 * Renders legacy plain text that may carry `[Термин|Объяснение]` markup.
 * Rich (TipTap JSON) bodies go through RichContent instead -- see
 * `utils/richContent.ts` for how the two are told apart.
 */
const props = defineProps<{ text: string }>();

const segments = computed(() => parseGlossary(props.text));
</script>

<template>
  <span>
    <template v-for="(segment, i) in segments" :key="i">
      <template v-if="segment.type === 'text'">{{ segment.value }}</template>
      <GlossaryTooltip v-else :term="segment.term" :explanation="segment.explanation" />
    </template>
  </span>
</template>
