<script setup lang="ts">
import { computed } from "vue";

import MathView from "@/components/richtext/MathView.vue";
import GlossaryTooltip from "@/components/shared/GlossaryTooltip.vue";
import { hasMath, parseMath } from "@/utils/math";
import type { RichNode } from "@/utils/richContent";

/**
 * One text node with its marks applied. Most marks are just classes, so they
 * compose freely; the two that need a real wrapper element (a glossary term
 * and a link) are handled explicitly and never both apply to one span.
 */
const props = defineProps<{ node: RichNode }>();

function mark(type: string) {
  return props.node.marks?.find((m) => m.type === type);
}

const classes = computed(() => {
  const out: string[] = [];
  if (mark("bold")) out.push("font-semibold");
  if (mark("italic")) out.push("italic");
  if (mark("underline")) out.push("underline underline-offset-2");
  if (mark("strike")) out.push("line-through");
  if (mark("code")) out.push("rounded bg-paper-2 px-1 py-0.5 font-mono text-[0.9em]");
  if (mark("highlight")) out.push("rounded bg-marigold/25 px-0.5");
  return out.join(" ");
});

// Only a named palette is honoured -- an arbitrary attacker-supplied colour
// string never reaches the style attribute.
const SAFE_COLORS: Record<string, string> = {
  teal: "rgb(13 148 136)",
  blue: "rgb(37 99 235)",
  green: "rgb(21 128 61)",
  amber: "rgb(180 83 9)",
  red: "rgb(220 38 38)",
  purple: "rgb(126 34 206)",
};

const colorStyle = computed(() => {
  const value = mark("textStyle")?.attrs?.color;
  if (typeof value !== "string") return undefined;
  const resolved = SAFE_COLORS[value];
  return resolved ? { color: resolved } : undefined;
});

const glossary = computed(() => {
  const explanation = mark("glossaryTerm")?.attrs?.explanation;
  return typeof explanation === "string" && explanation ? explanation : null;
});

/**
 * Lessons written before the editor understood maths still hold raw `$…$`
 * text, so it is split out here too rather than showing the student stray
 * dollar signs. Newer documents carry real inlineMath nodes and skip this.
 */
const mathSegments = computed(() => {
  const text = props.node.text ?? "";
  return hasMath(text) ? parseMath(text) : null;
});

// Only http(s) and mailto survive -- blocks `javascript:` and `data:` URLs.
const href = computed(() => {
  const value = mark("link")?.attrs?.href;
  if (typeof value !== "string") return null;
  return /^(https?:|mailto:)/i.test(value.trim()) ? value.trim() : null;
});
</script>

<template>
  <GlossaryTooltip v-if="glossary" :term="node.text ?? ''" :explanation="glossary" />
  <a
    v-else-if="href"
    :href="href"
    target="_blank"
    rel="noopener noreferrer nofollow"
    class="text-moss underline underline-offset-2 hover:opacity-80"
    :class="classes"
    :style="colorStyle"
    >{{ node.text }}</a
  >
  <span v-else :class="classes" :style="colorStyle">
    <template v-if="mathSegments">
      <template v-for="(segment, i) in mathSegments" :key="i">
        <MathView v-if="segment.type === 'math'" :latex="segment.latex" />
        <template v-else>{{ segment.value }}</template>
      </template>
    </template>
    <template v-else>{{ node.text }}</template>
  </span>
</template>
