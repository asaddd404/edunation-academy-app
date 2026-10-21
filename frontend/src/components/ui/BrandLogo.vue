<script setup lang="ts">
/**
 * The Edunation Academy logo, in the right colourway for where it sits.
 *
 * `onColor` is for the brand header (teal, or near-black in dark mode): the
 * white logo, always. Elsewhere the full-colour logo is shown on the light
 * theme and the white one on the dark theme, where the navy wordmark would
 * disappear into the background.
 */
withDefaults(defineProps<{ layout?: "horizontal" | "vertical"; onColor?: boolean }>(), {
  layout: "horizontal",
  onColor: false,
});
</script>

<template>
  <span class="inline-flex">
    <img
      v-if="onColor"
      :src="`/brand/logo-${layout}-white.webp`"
      alt="Edunation Academy"
      class="h-full w-auto"
      draggable="false"
    />
    <template v-else>
      <img :src="`/brand/logo-${layout}.webp`" alt="Edunation Academy" class="h-full w-auto dark:hidden" draggable="false" />
      <img
        :src="`/brand/logo-${layout}-white.webp`"
        alt="Edunation Academy"
        class="hidden h-full w-auto dark:block"
        draggable="false"
      />
    </template>
  </span>
</template>
