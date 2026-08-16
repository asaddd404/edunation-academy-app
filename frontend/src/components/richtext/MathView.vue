<script setup lang="ts">
import katex from "katex";
import "katex/dist/katex.min.css";
import { onMounted, ref, watch } from "vue";

/**
 * Renders one LaTeX expression with KaTeX.
 *
 * Uses `katex.render(source, element)` -- the DOM API -- rather than
 * `renderToString` + `v-html`, so this component keeps the same "never inject
 * an HTML string" property as the rest of the renderer.
 *
 * `trust: false` is what makes teacher-authored LaTeX safe: KaTeX then refuses
 * to emit links or raw HTML for commands like `\href`, rendering the source as
 * inert glyphs instead. `throwOnError: false` means a typo shows up as red
 * source text for the student instead of blanking the lesson.
 */
const props = defineProps<{ latex: string; display?: boolean }>();

const host = ref<HTMLElement | null>(null);

function render() {
  if (!host.value) return;
  katex.render(props.latex, host.value, {
    displayMode: Boolean(props.display),
    throwOnError: false,
    trust: false,
    output: "html",
  });
}

onMounted(render);
watch(() => [props.latex, props.display], render);
</script>

<template>
  <div v-if="display" ref="host" class="my-2 overflow-x-auto" />
  <span v-else ref="host" />
</template>
