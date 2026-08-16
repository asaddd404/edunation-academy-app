import { computed, onBeforeUnmount, ref } from "vue";

/**
 * Ticking countdown for a timed ЕНТ simulation. The server is the source of
 * truth for how much time is left (`expires_at` survives page reloads on its
 * own) -- this only re-derives a local per-second display from whatever
 * remaining-seconds value the caller starts it with, and fires `onExpire`
 * once when it reaches zero.
 */
export function useExamTimer(onExpire: () => void) {
  const remainingSeconds = ref<number | null>(null);
  let handle: number | undefined;

  function stop() {
    if (handle !== undefined) {
      clearInterval(handle);
      handle = undefined;
    }
  }

  function start(initialSeconds: number | null) {
    stop();
    remainingSeconds.value = initialSeconds;
    if (initialSeconds === null) return;
    if (initialSeconds <= 0) {
      remainingSeconds.value = 0;
      onExpire();
      return;
    }
    handle = window.setInterval(() => {
      if (remainingSeconds.value === null) return;
      remainingSeconds.value -= 1;
      if (remainingSeconds.value <= 0) {
        remainingSeconds.value = 0;
        stop();
        onExpire();
      }
    }, 1000);
  }

  // Always ЧЧ:ММ:СС -- an ЕНТ attempt can run up to 4 hours, so the hour
  // digits matter and shouldn't pop in/out as time crosses the 1h mark.
  const label = computed(() => {
    if (remainingSeconds.value === null) return null;
    const total = remainingSeconds.value;
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  });

  const isCritical = computed(() => remainingSeconds.value !== null && remainingSeconds.value <= 300);

  onBeforeUnmount(stop);

  return { remainingSeconds, label, isCritical, start, stop };
}
