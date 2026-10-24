import { isAxiosError } from "axios";
import { onBeforeUnmount, ref } from "vue";

import { saveEntAnswers } from "@/api/ent";
import type { AnswerPayload, NullableAnswer } from "@/types";

/**
 * Keeps an ЕНТ attempt's answers safe while the student works.
 *
 * Two copies, for two different failures:
 *   - localStorage, written synchronously on every change -- survives a
 *     reload, a crashed tab, a dead connection;
 *   - the server (PUT /ent/simulations/{id}/answers), sent in the background
 *     -- survives a different device, and is what the server grades if the
 *     attempt is closed for the student when time runs out.
 *
 * Changes are batched (one request per DEBOUNCE_MS of activity), retried
 * with backoff while the network is down, and flushed again on `online`
 * and when the tab is hidden. A question changed while its save is in
 * flight stays pending and goes out with the next batch.
 */

export type AutosaveState = "idle" | "saving" | "saved" | "offline" | "error";

const DEBOUNCE_MS = 800;
const RETRY_DELAYS_MS = [2000, 5000, 10000, 30000];
const KEY_PREFIX = "ent-draft:";
const STALE_AFTER_MS = 2 * 24 * 60 * 60 * 1000;

interface StoredDraft {
  answers: Record<string, AnswerPayload>;
  pending: number[];
  savedAt: number;
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null; // private mode / blocked site data: server copy only
  }
}

/** Drafts of attempts long finished or abandoned. */
function dropStaleDrafts(store: Storage) {
  for (let i = store.length - 1; i >= 0; i--) {
    const key = store.key(i);
    if (!key?.startsWith(KEY_PREFIX)) continue;
    try {
      const draft = JSON.parse(store.getItem(key) ?? "null") as StoredDraft | null;
      if (!draft || Date.now() - draft.savedAt > STALE_AFTER_MS) store.removeItem(key);
    } catch {
      store.removeItem(key);
    }
  }
}

/** The server echoes unset fields as null; the exam screen wants them absent. */
function clean(answer: NullableAnswer): AnswerPayload {
  const out: AnswerPayload = { question_id: answer.question_id };
  for (const [field, value] of Object.entries(answer)) {
    if (value !== null && value !== undefined) (out as unknown as Record<string, unknown>)[field] = value;
  }
  return out;
}

export function useAnswerAutosave(simulationId: number, answers: Record<number, AnswerPayload>) {
  const key = `${KEY_PREFIX}${simulationId}`;
  const store = storage();
  const pending = new Set<number>();
  const state = ref<AutosaveState>("idle");

  let timer: ReturnType<typeof setTimeout> | undefined;
  let retry = 0;
  let inFlight = false;
  let stopped = false;

  function writeLocal() {
    if (!store) return;
    const draft: StoredDraft = { answers: { ...answers }, pending: [...pending], savedAt: Date.now() };
    try {
      store.setItem(key, JSON.stringify(draft));
    } catch {
      // quota full: the server copy still goes out
    }
  }

  function readLocal(): StoredDraft | null {
    try {
      return JSON.parse(store?.getItem(key) ?? "null") as StoredDraft | null;
    } catch {
      return null;
    }
  }

  function schedule(delay: number) {
    if (stopped) return;
    clearTimeout(timer);
    timer = setTimeout(() => void flush(), delay);
  }

  /**
   * Fills `answers` on load: what the server has, then anything this
   * device changed but never got to the server (offline, closed mid-save).
   * Local-but-synced answers are not reapplied -- the server copy is as new
   * or newer (another device may have changed them since).
   */
  function restore(serverAnswers: NullableAnswer[], questionIds: number[]) {
    if (store) dropStaleDrafts(store);
    const valid = new Set(questionIds);
    for (const answer of serverAnswers) answers[answer.question_id] = clean(answer);
    const local = readLocal();
    for (const id of local?.pending ?? []) {
      if (!valid.has(id)) continue;
      const answer = local?.answers[String(id)];
      if (answer) answers[id] = answer;
      else delete answers[id];
      pending.add(id);
    }
    writeLocal();
    state.value = pending.size ? "saving" : "saved";
    if (pending.size) schedule(0);
  }

  /** Call after every change to one question's answer. */
  function record(questionId: number) {
    if (stopped) return;
    pending.add(questionId);
    writeLocal();
    state.value = navigator.onLine ? "saving" : "offline";
    schedule(DEBOUNCE_MS);
  }

  async function flush(): Promise<void> {
    if (stopped || inFlight || pending.size === 0) return;
    if (!navigator.onLine) {
      state.value = "offline"; // the `online` listener resumes
      return;
    }
    inFlight = true;
    state.value = "saving";
    const batch = [...pending];
    const sent = new Map(batch.map((id) => [id, JSON.stringify(answers[id] ?? null)]));
    try {
      // An absent answer is sent as just the id, which clears it server-side.
      await saveEntAnswers(simulationId, batch.map((id) => answers[id] ?? { question_id: id }));
      for (const id of batch) {
        if (JSON.stringify(answers[id] ?? null) === sent.get(id)) pending.delete(id);
      }
      retry = 0;
      writeLocal();
      state.value = pending.size ? "saving" : "saved";
      if (pending.size) schedule(DEBOUNCE_MS);
    } catch (error) {
      if (isAxiosError(error) && error.response?.status === 409) {
        // Attempt closed (submitted elsewhere, or time is over): nothing
        // more can be saved; the exam screen handles the result.
        stopped = true;
        state.value = "idle";
        return;
      }
      state.value = navigator.onLine ? "error" : "offline";
      schedule(RETRY_DELAYS_MS[Math.min(retry++, RETRY_DELAYS_MS.length - 1)]);
    } finally {
      inFlight = false;
    }
  }

  function onOnline() {
    retry = 0;
    void flush();
  }
  function onOffline() {
    if (pending.size) state.value = "offline";
  }
  function onHidden() {
    if (document.visibilityState === "hidden") void flush();
  }

  window.addEventListener("online", onOnline);
  window.addEventListener("offline", onOffline);
  window.addEventListener("pagehide", onHidden);
  document.addEventListener("visibilitychange", onHidden);

  function stop() {
    stopped = true;
    clearTimeout(timer);
    window.removeEventListener("online", onOnline);
    window.removeEventListener("offline", onOffline);
    window.removeEventListener("pagehide", onHidden);
    document.removeEventListener("visibilitychange", onHidden);
  }

  /** After a successful submit: the draft has served its purpose. */
  function clear() {
    stop();
    pending.clear();
    try {
      store?.removeItem(key);
    } catch {
      // nothing to clean up
    }
  }

  // Leaving the page (in-app navigation): one last attempt to get pending
  // answers out; the local draft covers it if that fails.
  onBeforeUnmount(() => {
    void flush();
    stop();
  });

  return { state, restore, record, flush, clear, hasPending: () => pending.size > 0 };
}
