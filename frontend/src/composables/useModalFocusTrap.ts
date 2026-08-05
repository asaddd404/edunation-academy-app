import { nextTick, watch, type Ref } from "vue";

/**
 * Focus containment for a modal: moves focus in when its root element
 * mounts, traps Tab/Shift+Tab inside it, closes on Escape, and restores
 * focus to whatever triggered it when the root unmounts.
 *
 * Driven off the root element ref transitioning between null and an
 * element rather than component lifecycle, so it works the same whether
 * the modal is its own component (mounts/unmounts with it) or an inline
 * `v-if` block inside a longer-lived parent.
 *
 * Deliberately focuses the first focusable element rather than a specific
 * button: in every modal this is used on, that's either a form field or a
 * secondary/cancel action, never the destructive confirm button, so it
 * satisfies "confirm isn't focused by default" without hardcoding which
 * element that is per modal.
 */
const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusableElements(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (el) => el.offsetParent !== null,
  );
}

export function useModalFocusTrap(rootRef: Ref<HTMLElement | null>, onClose: () => void) {
  let triggerElement: HTMLElement | null = null;

  function handleKeydown(event: KeyboardEvent) {
    const root = rootRef.value;
    if (!root) return;

    if (event.key === "Escape") {
      event.stopPropagation();
      onClose();
      return;
    }
    if (event.key !== "Tab") return;

    const items = focusableElements(root);
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  watch(rootRef, async (el, previousEl) => {
    if (el && !previousEl) {
      triggerElement = document.activeElement as HTMLElement | null;
      document.addEventListener("keydown", handleKeydown, true);
      await nextTick();
      const items = focusableElements(el);
      (items[0] ?? el).focus();
    } else if (!el && previousEl) {
      document.removeEventListener("keydown", handleKeydown, true);
      triggerElement?.focus();
      triggerElement = null;
    }
  });
}
