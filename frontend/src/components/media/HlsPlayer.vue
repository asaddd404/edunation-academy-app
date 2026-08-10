<script setup lang="ts">
import Hls from "hls.js";
import { onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps<{ src: string }>();

const videoRef = ref<HTMLVideoElement | null>(null);
const error = ref<string | null>(null);
let hls: Hls | null = null;

function destroy() {
  hls?.destroy();
  hls = null;
}

function attach(src: string) {
  destroy();
  error.value = null;
  const video = videoRef.value;
  if (!video) return;

  if (Hls.isSupported()) {
    hls = new Hls();
    hls.on(Hls.Events.ERROR, (_event, data) => {
      if (data.fatal) error.value = "Не удалось загрузить видео";
    });
    hls.loadSource(src);
    hls.attachMedia(video);
  } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
    video.src = src;
  } else {
    error.value = "Ваш браузер не поддерживает воспроизведение видео";
  }
}

onMounted(() => attach(props.src));
watch(() => props.src, attach);
onBeforeUnmount(destroy);
</script>

<template>
  <div class="overflow-hidden rounded-xl bg-black">
    <video ref="videoRef" controls class="aspect-video w-full" />
    <p v-if="error" class="bg-clay/15 p-3 text-sm text-clay">{{ error }}</p>
  </div>
</template>
