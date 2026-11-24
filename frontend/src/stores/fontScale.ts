import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";

/**
 * «A+»: bigger text across the whole site, for anyone who finds the default
 * small. Every size in the design is in rem, so scaling the root font size
 * scales text, buttons and spacing together without breaking the layout.
 * Remembered on this device.
 */
const KEY = "edunation_font_scale";
export const FONT_STEPS = [100, 112.5, 125] as const;
const LABELS = ["Обычный", "Крупный", "Очень крупный"];

function initial(): number {
  try {
    const stored = Number(localStorage.getItem(KEY));
    const index = FONT_STEPS.indexOf(stored as (typeof FONT_STEPS)[number]);
    return index >= 0 ? index : 0;
  } catch {
    return 0;
  }
}

function apply(index: number) {
  document.documentElement.style.fontSize = index === 0 ? "" : `${FONT_STEPS[index]}%`;
}

export const useFontScaleStore = defineStore("fontScale", () => {
  const index = ref(initial());
  apply(index.value);
  watch(index, (value) => {
    apply(value);
    try {
      localStorage.setItem(KEY, String(FONT_STEPS[value]));
    } catch {
      /* private mode: the size just isn't remembered */
    }
  });

  const label = computed(() => LABELS[index.value]);
  /** Cycles Обычный → Крупный → Очень крупный → Обычный. */
  function next() {
    index.value = (index.value + 1) % FONT_STEPS.length;
  }
  return { index, label, next };
});
