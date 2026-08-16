<script setup lang="ts">
import {
  Atom,
  BookOpen,
  Dna,
  FlaskConical,
  Globe,
  Languages,
  Monitor,
  Scroll,
  Sigma,
} from "@lucide/vue";
import { computed, type Component } from "vue";

/**
 * Subject glyph, matched by name.
 *
 * Replaces the emoji that `subjectTheme` used to carry: emoji are drawn by
 * the OS font, so the same subject looked different on every machine and
 * could not take the theme colour. Lucide icons inherit `currentColor` and
 * sit on the same grid as the rest of the icon set.
 */
const props = defineProps<{ name: string }>();

const MATCHERS: { match: RegExp; icon: Component }[] = [
  { match: /матем|алгебр|геометр/i, icon: Sigma },
  { match: /хими/i, icon: FlaskConical },
  { match: /физик/i, icon: Atom },
  { match: /биолог/i, icon: Dna },
  { match: /истори/i, icon: Scroll },
  { match: /географ/i, icon: Globe },
  { match: /информат|программ/i, icon: Monitor },
  { match: /англ|рус|казах|қазақ|язык|тіл/i, icon: Languages },
];

const icon = computed<Component>(() => MATCHERS.find((m) => m.match.test(props.name))?.icon ?? BookOpen);
</script>

<template>
  <component :is="icon" :stroke-width="1.7" aria-hidden="true" />
</template>
