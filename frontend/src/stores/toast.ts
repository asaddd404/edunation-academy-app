import { defineStore } from "pinia";
import { ref } from "vue";

export type ToastTone = "error" | "success" | "info";

export interface Toast {
  id: number;
  tone: ToastTone;
  message: string;
}

let nextId = 0;

/** Short notices that are not tied to one place on the page -- above all,
 * failures that would otherwise leave the user staring at an unchanged
 * screen with no idea the click did nothing. */
export const useToastStore = defineStore("toast", () => {
  const items = ref<Toast[]>([]);

  function dismiss(id: number) {
    items.value = items.value.filter((t) => t.id !== id);
  }

  function push(message: string, tone: ToastTone = "error", timeoutMs = 6000) {
    // The same failure repeated (a button clicked three times) is one toast.
    if (items.value.some((t) => t.message === message && t.tone === tone)) return;
    const id = ++nextId;
    items.value = [...items.value.slice(-2), { id, tone, message }];
    window.setTimeout(() => dismiss(id), timeoutMs);
  }

  return { items, push, dismiss };
});
