import { onBeforeUnmount, readonly, ref } from "vue";

/**
 * Reactive `matchMedia`, for the cases where a layout differs structurally
 * between breakpoints rather than just visually -- e.g. the catalog, which
 * renders cascading columns on a desktop and a step-by-step drill-down on a
 * phone. A CSS-only `hidden md:block` pair cannot express that: it would
 * mount both trees and fire both sets of requests.
 */
export function useMediaQuery(query: string) {
  const matches = ref(false);

  // Guard for SSR / non-browser environments; the app is SPA-only today but
  // this composable is the kind of thing that gets reused.
  if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
    const media = window.matchMedia(query);
    matches.value = media.matches;

    const update = (event: MediaQueryListEvent) => {
      matches.value = event.matches;
    };
    media.addEventListener("change", update);
    onBeforeUnmount(() => media.removeEventListener("change", update));
  }

  return readonly(matches);
}
