import { onBeforeUnmount } from "vue";

import { pingActivity } from "@/api/activity";

const PING_INTERVAL_MS = 60_000;

/**
 * Pings the backend once a minute to credit active time, but only while the
 * tab is actually visible -- a `visibilitychange` listener tears the
 * interval down the instant the tab is hidden (rather than just skipping a
 * ping while hidden), so backgrounding is an immediate pause, not a delayed
 * one, and resumes cleanly on return without a burst of catch-up pings.
 */
export function useActivityTracker() {
  let handle: ReturnType<typeof setInterval> | null = null;

  function startInterval() {
    if (handle !== null) return;
    handle = setInterval(pingActivity, PING_INTERVAL_MS);
  }

  function stopInterval() {
    if (handle !== null) {
      clearInterval(handle);
      handle = null;
    }
  }

  function handleVisibilityChange() {
    if (document.visibilityState === "visible") startInterval();
    else stopInterval();
  }

  function start() {
    if (document.visibilityState === "visible") startInterval();
    document.addEventListener("visibilitychange", handleVisibilityChange);
  }

  function stop() {
    stopInterval();
    document.removeEventListener("visibilitychange", handleVisibilityChange);
  }

  onBeforeUnmount(stop);

  return { start, stop };
}
