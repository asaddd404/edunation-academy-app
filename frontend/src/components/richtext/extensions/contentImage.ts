import Image from "@tiptap/extension-image";
import { mergeAttributes } from "@tiptap/core";

import { getLessonContentImageUrl } from "@/api/lessons";

export type ImageSize = "small" | "medium" | "full";

export const IMAGE_SIZES: { value: ImageSize; label: string }[] = [
  { value: "small", label: "Маленькое" },
  { value: "medium", label: "Среднее" },
  { value: "full", label: "По ширине" },
];

// Kept in sync with IMAGE_WIDTHS in RichNodeView.vue.
const EDITOR_WIDTHS: Record<ImageSize, string> = {
  small: "max-w-[240px]",
  medium: "max-w-[480px]",
  full: "w-full",
};

/**
 * The stock Image node plus a `size` attribute, which is what makes the
 * teacher's "маленькое изображение" request work: the node stores an intent
 * ("small") rather than a pixel width, so the student view can pick its own
 * responsive width for that intent.
 *
 * `src` holds our relative upload path (`lesson-content/<uuid>.png`), not a
 * URL -- RichNodeView resolves it. That keeps stored documents portable if
 * the API host ever changes.
 */
export const ContentImage = Image.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      size: {
        default: "medium" as ImageSize,
        parseHTML: (element) => element.getAttribute("data-size") ?? "medium",
        renderHTML: (attributes) => ({ "data-size": attributes.size }),
      },
    };
  },

  // The `src` attribute stays relative, but the DOM the editor paints needs a
  // real URL or the teacher just sees a broken image. Resolving here (rather
  // than storing an absolute URL) keeps getJSON() -- and therefore what gets
  // saved -- relative.
  renderHTML({ HTMLAttributes, node }) {
    const size = (node.attrs.size as ImageSize) ?? "medium";
    const src = typeof node.attrs.src === "string" ? node.attrs.src : "";
    return [
      "img",
      mergeAttributes(HTMLAttributes, {
        src: src ? getLessonContentImageUrl(src) : "",
        class: `h-auto rounded-lg border border-line ${EDITOR_WIDTHS[size] ?? EDITOR_WIDTHS.medium}`,
      }),
    ];
  },
});
