<script setup lang="ts">
import { computed } from "vue";

import { youtubeVideoId } from "@/utils/youtube";

/**
 * A lesson video hosted on YouTube. Played from youtube-nocookie.com, which
 * sets no tracking cookies until the student presses play, and loaded lazily
 * so a lesson page does not pull in the player before it is scrolled to.
 */
const props = defineProps<{ url: string; title: string }>();

const src = computed(() => {
  const id = youtubeVideoId(props.url);
  return id ? `https://www.youtube-nocookie.com/embed/${id}?rel=0&modestbranding=1` : null;
});
</script>

<template>
  <div v-if="src" class="aspect-video w-full overflow-hidden rounded-2xl border border-line bg-black shadow-sm">
    <iframe
      :src="src"
      :title="`Видео: ${title}`"
      class="h-full w-full"
      loading="lazy"
      referrerpolicy="strict-origin-when-cross-origin"
      allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
      allowfullscreen
    />
  </div>
</template>
