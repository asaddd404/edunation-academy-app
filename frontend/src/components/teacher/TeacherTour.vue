<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";

import { useTeacherHelpStore } from "@/stores/teacherHelp";

/**
 * A few hints on the teacher's first visit: dims the page, lights up one
 * element at a time and says in a sentence what it's for. Shown once per
 * device; «Помощь» can start it again. A step whose element isn't on screen
 * (say, a menu link hidden on a phone) shows its card without the highlight.
 */
export interface TourStep {
  target: string; // matches data-tour="…"
  title: string;
  text: string;
}

const props = defineProps<{ steps: TourStep[] }>();
const help = useTeacherHelpStore();

const index = ref(0);
const rect = ref<DOMRect | null>(null);
const cardEl = ref<HTMLElement | null>(null);
const step = computed(() => props.steps[index.value]);
const isLast = computed(() => index.value === props.steps.length - 1);

function findTarget(name: string): HTMLElement | null {
  const all = Array.from(document.querySelectorAll<HTMLElement>(`[data-tour="${name}"]`));
  return all.find((el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  }) ?? null;
}

function measure() {
  const el = step.value ? findTarget(step.value.target) : null;
  rect.value = el ? el.getBoundingClientRect() : null;
}

async function show() {
  const el = step.value ? findTarget(step.value.target) : null;
  if (el) {
    const r = el.getBoundingClientRect();
    if (r.top < 80 || r.bottom > window.innerHeight - 220) el.scrollIntoView({ block: "center" });
  }
  await nextTick();
  measure();
  cardEl.value?.focus();
}

function next() {
  if (isLast.value) return finish();
  index.value += 1;
  void show();
}
function finish() {
  help.finishTour();
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") finish();
}

watch(
  () => help.tourActive,
  async (active) => {
    if (active) {
      index.value = 0;
      window.addEventListener("resize", measure);
      window.addEventListener("scroll", measure, true);
      document.addEventListener("keydown", onKey);
      await nextTick();
      void show();
    } else {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
      document.removeEventListener("keydown", onKey);
    }
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  window.removeEventListener("resize", measure);
  window.removeEventListener("scroll", measure, true);
  document.removeEventListener("keydown", onKey);
});

const PAD = 6;
const box = computed(() => {
  const r = rect.value;
  if (!r) return null;
  return { top: r.top - PAD, left: r.left - PAD, width: r.width + PAD * 2, height: r.height + PAD * 2 };
});

// The card goes under the highlighted element, or above it when there's no
// room below; without a target it sits in the middle of the screen.
const cardStyle = computed(() => {
  const b = box.value;
  const width = Math.min(380, window.innerWidth - 32);
  if (!b) return { width: `${width}px`, left: "50%", top: "50%", transform: "translate(-50%, -50%)" };
  const left = Math.min(Math.max(16, b.left), window.innerWidth - width - 16);
  const cardHeight = cardEl.value?.offsetHeight || 230;
  const below = b.top + b.height + 12;
  if (below + cardHeight + 16 <= window.innerHeight) return { width: `${width}px`, left: `${left}px`, top: `${below}px` };
  if (b.top - 12 - cardHeight >= 16) return { width: `${width}px`, left: `${left}px`, bottom: `${window.innerHeight - b.top + 12}px` };
  // No room on either side (a tall element on a phone): pin to the bottom.
  return { width: `${width}px`, left: `${left}px`, bottom: "16px" };
});
</script>

<template>
  <Teleport to="body">
    <div v-if="help.tourActive && step" class="fixed inset-0 z-[80]" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      <!-- Dim everything; the highlight cuts a window with its huge shadow. -->
      <div v-if="!box" class="absolute inset-0 bg-black/50" />
      <div
        v-else
        class="pointer-events-none absolute rounded-2xl ring-4 ring-marigold transition-all duration-200"
        :style="{
          top: `${box.top}px`,
          left: `${box.left}px`,
          width: `${box.width}px`,
          height: `${box.height}px`,
          boxShadow: '0 0 0 9999px rgba(0,0,0,0.5)',
        }"
      />
      <div ref="cardEl" tabindex="-1" class="absolute space-y-3 rounded-2xl bg-paper p-5 shadow-2xl outline-none" :style="cardStyle">
        <p class="text-sm font-semibold text-moss">Подсказка {{ index + 1 }} из {{ steps.length }}</p>
        <h2 id="tour-title" class="text-xl font-bold text-ink">{{ step.title }}</h2>
        <p class="text-ink-2">{{ step.text }}</p>
        <div class="flex flex-wrap items-center justify-between gap-2 pt-1">
          <button type="button" class="min-h-11 rounded-xl px-3 font-semibold text-ink-2 hover:bg-paper-2" @click="finish">Пропустить</button>
          <button type="button" class="btn-primary min-h-12 px-6 text-base" @click="next">{{ isLast ? "Понятно" : "Далее →" }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
