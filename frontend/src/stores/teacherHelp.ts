import { defineStore } from "pinia";
import { ref } from "vue";

/** The «Помощь» side panel and the first-visit tour, opened from anywhere. */
const TOUR_KEY = "edunation_teacher_tour_done";

function tourDone(): boolean {
  try {
    return localStorage.getItem(TOUR_KEY) === "1";
  } catch {
    return true; // can't remember it: never nag on every visit
  }
}

export const useTeacherHelpStore = defineStore("teacherHelp", () => {
  const open = ref(false);
  const topic = ref<string | null>(null);
  const tourActive = ref(false);

  function show(which: string | null = null) {
    topic.value = which;
    open.value = true;
  }
  function close() {
    open.value = false;
  }
  function startTour() {
    open.value = false;
    tourActive.value = true;
  }
  function maybeStartTour() {
    if (!tourDone()) tourActive.value = true;
  }
  function finishTour() {
    tourActive.value = false;
    try {
      localStorage.setItem(TOUR_KEY, "1");
    } catch {
      /* ignore */
    }
  }
  return { open, topic, tourActive, show, close, startTour, maybeStartTour, finishTour };
});
