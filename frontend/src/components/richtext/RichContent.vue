<script setup lang="ts">
import { computed } from "vue";

import RichNodeView from "@/components/richtext/RichNodeView.vue";
import SmartText from "@/components/shared/SmartText.vue";
import { isRichDocEmpty, parseRichContent } from "@/utils/richContent";

/**
 * Renders a lesson body, whichever format it is stored in: a TipTap document
 * from the new editor, or legacy plain text with `[Термин|Объяснение]`
 * markup. Every caller should use this rather than picking a renderer, so
 * old and new lessons stay interchangeable.
 */
const props = defineProps<{ content: string | null | undefined }>();

const parsed = computed(() => parseRichContent(props.content));

const isEmpty = computed(() => {
  const value = parsed.value;
  if (value.kind === "empty") return true;
  return value.kind === "rich" && isRichDocEmpty(value.doc);
});
</script>

<template>
  <div v-if="!isEmpty" class="rich-content">
    <template v-if="parsed.kind === 'rich'">
      <RichNodeView v-for="(node, i) in parsed.doc.content ?? []" :key="i" :node="node" />
    </template>
    <p v-else-if="parsed.kind === 'plain'" class="whitespace-pre-line">
      <SmartText :text="parsed.text" />
    </p>
  </div>
</template>
