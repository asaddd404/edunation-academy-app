<script setup lang="ts">
import { onBeforeUnmount, ref } from "vue";
import { useRouter } from "vue-router";

/**
 * A thin bar at the top while a navigation is pending -- mostly the download
 * of the next page's chunk on a slow connection. Without it the old page just
 * sits there after a click and reads as a frozen site. It appears only after
 * a short delay, so instant (cached / prefetched) navigations never flash it.
 */
const SHOW_AFTER_MS = 120;

const router = useRouter();
const visible = ref(false);
const done = ref(false);
let timer: ReturnType<typeof setTimeout> | undefined;

function finish() {
  clearTimeout(timer);
  if (!visible.value) return;
  done.value = true;
  timer = setTimeout(() => {
    visible.value = false;
    done.value = false;
  }, 250);
}

const stopBefore = router.beforeEach(() => {
  clearTimeout(timer);
  done.value = false;
  timer = setTimeout(() => (visible.value = true), SHOW_AFTER_MS);
});
const stopAfter = router.afterEach(finish);
const stopError = router.onError(finish);

onBeforeUnmount(() => {
  clearTimeout(timer);
  stopBefore();
  stopAfter();
  stopError();
});
</script>

<template>
  <div
    v-if="visible"
    class="pointer-events-none fixed inset-x-0 top-0 z-[60] h-0.5 overflow-hidden"
    role="progressbar"
    aria-label="Загрузка страницы"
  >
    <div class="route-progress h-full bg-brand-glow" :class="{ 'route-progress--done': done }" />
  </div>
</template>

<style scoped>
.route-progress {
  width: 85%;
  transform-origin: left;
  animation: route-progress-grow 8s cubic-bezier(0.1, 0.7, 0.2, 1) forwards;
}
.route-progress--done {
  width: 100%;
  animation: none;
  opacity: 0;
  transition: opacity 250ms ease 100ms;
}
@keyframes route-progress-grow {
  from {
    transform: scaleX(0.05);
  }
  to {
    transform: scaleX(1);
  }
}
@media (prefers-reduced-motion: reduce) {
  .route-progress {
    animation: none;
  }
}
</style>
