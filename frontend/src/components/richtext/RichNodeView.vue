<script setup lang="ts">
import { computed } from "vue";

import { getLessonContentImageUrl } from "@/api/lessons";
import MathView from "@/components/richtext/MathView.vue";
import RichTextSpan from "@/components/richtext/RichTextSpan.vue";
import type { RichNode } from "@/utils/richContent";

/**
 * Recursively renders one TipTap node as real Vue elements.
 *
 * Deliberately never uses `v-html`: the document is authored by teachers and
 * stored verbatim, so building the tree out of components is what makes an
 * injected `<script>` impossible rather than merely sanitized away. Unknown
 * node types render their children instead of disappearing, so a document
 * from a newer editor build degrades rather than losing its text.
 */
const props = defineProps<{ node: RichNode }>();

const children = computed(() => props.node.content ?? []);

const headingTag = computed(() => {
  const level = Number(props.node.attrs?.level ?? 2);
  return level <= 2 ? "h2" : level === 3 ? "h3" : "h4";
});

const IMAGE_WIDTHS: Record<string, string> = {
  small: "max-w-[240px]",
  medium: "max-w-[480px]",
  full: "w-full",
};
const imageClass = computed(() => IMAGE_WIDTHS[String(props.node.attrs?.size ?? "medium")] ?? IMAGE_WIDTHS.medium);

const imageSrc = computed(() => {
  const src = props.node.attrs?.src;
  return typeof src === "string" ? getLessonContentImageUrl(src) : "";
});

const CALLOUT_TONES: Record<string, string> = {
  info: "border-moss/40 bg-moss/10",
  success: "border-green-600/40 bg-green-600/10",
  warning: "border-amber-600/40 bg-amber-600/10",
  danger: "border-red-600/40 bg-red-600/10",
};
const calloutClass = computed(
  () => CALLOUT_TONES[String(props.node.attrs?.variant ?? "info")] ?? CALLOUT_TONES.info,
);
</script>

<template>
  <RichTextSpan v-if="node.type === 'text'" :node="node" />

  <br v-else-if="node.type === 'hardBreak'" />

  <MathView v-else-if="node.type === 'inlineMath'" :latex="String(node.attrs?.latex ?? '')" />

  <MathView v-else-if="node.type === 'blockMath'" :latex="String(node.attrs?.latex ?? '')" display />

  <p v-else-if="node.type === 'paragraph'">
    <RichNodeView v-for="(child, i) in children" :key="i" :node="child" />
  </p>

  <component :is="headingTag" v-else-if="node.type === 'heading'">
    <RichNodeView v-for="(child, i) in children" :key="i" :node="child" />
  </component>

  <ul v-else-if="node.type === 'bulletList'">
    <RichNodeView v-for="(child, i) in children" :key="i" :node="child" />
  </ul>

  <ol v-else-if="node.type === 'orderedList'">
    <RichNodeView v-for="(child, i) in children" :key="i" :node="child" />
  </ol>

  <li v-else-if="node.type === 'listItem'">
    <RichNodeView v-for="(child, i) in children" :key="i" :node="child" />
  </li>

  <blockquote v-else-if="node.type === 'blockquote'">
    <RichNodeView v-for="(child, i) in children" :key="i" :node="child" />
  </blockquote>

  <pre v-else-if="node.type === 'codeBlock'"><code><RichNodeView
    v-for="(child, i) in children" :key="i" :node="child"
  /></code></pre>

  <hr v-else-if="node.type === 'horizontalRule'" />

  <img
    v-else-if="node.type === 'image'"
    :src="imageSrc"
    :alt="String(node.attrs?.alt ?? '')"
    loading="lazy"
    class="h-auto rounded-lg border border-line"
    :class="imageClass"
  />

  <div v-else-if="node.type === 'callout'" class="rich-callout" :class="calloutClass">
    <RichNodeView v-for="(child, i) in children" :key="i" :node="child" />
  </div>

  <!-- Tables scroll inside their own box so a wide one never makes the whole
       lesson page scroll sideways on a phone. -->
  <div v-else-if="node.type === 'table'" class="overflow-x-auto">
    <table>
      <tbody>
        <RichNodeView v-for="(child, i) in children" :key="i" :node="child" />
      </tbody>
    </table>
  </div>

  <tr v-else-if="node.type === 'tableRow'">
    <RichNodeView v-for="(child, i) in children" :key="i" :node="child" />
  </tr>

  <th v-else-if="node.type === 'tableHeader'" :colspan="Number(node.attrs?.colspan ?? 1)" :rowspan="Number(node.attrs?.rowspan ?? 1)">
    <RichNodeView v-for="(child, i) in children" :key="i" :node="child" />
  </th>

  <td v-else-if="node.type === 'tableCell'" :colspan="Number(node.attrs?.colspan ?? 1)" :rowspan="Number(node.attrs?.rowspan ?? 1)">
    <RichNodeView v-for="(child, i) in children" :key="i" :node="child" />
  </td>

  <template v-else>
    <RichNodeView v-for="(child, i) in children" :key="i" :node="child" />
  </template>
</template>
