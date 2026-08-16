import { Node, mergeAttributes } from "@tiptap/core";

export type CalloutVariant = "info" | "success" | "warning" | "danger";

export const CALLOUT_VARIANTS: { value: CalloutVariant; label: string }[] = [
  { value: "info", label: "Заметка" },
  { value: "success", label: "Верно" },
  { value: "warning", label: "Важно" },
  { value: "danger", label: "Ошибка" },
];

// Kept in sync with CALLOUT_TONES in RichNodeView.vue -- the editor surface
// has to tint the same way the student view will.
const EDITOR_TONES: Record<CalloutVariant, string> = {
  info: "border-moss/40 bg-moss/10",
  success: "border-green-600/40 bg-green-600/10",
  warning: "border-amber-600/40 bg-amber-600/10",
  danger: "border-red-600/40 bg-red-600/10",
};

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    callout: {
      toggleCallout: (variant: CalloutVariant) => ReturnType;
    };
  }
}

/** A tinted box for "Важно" / "Подсказка" style asides inside a lesson. */
export const Callout = Node.create({
  name: "callout",
  group: "block",
  content: "block+",
  defining: true,

  addAttributes() {
    return {
      variant: {
        default: "info" as CalloutVariant,
        parseHTML: (element) => element.getAttribute("data-variant") ?? "info",
        renderHTML: (attributes) => ({ "data-variant": attributes.variant }),
      },
    };
  },

  parseHTML() {
    return [{ tag: "div[data-callout]" }];
  },

  renderHTML({ HTMLAttributes, node }) {
    const variant = (node.attrs.variant as CalloutVariant) ?? "info";
    return [
      "div",
      mergeAttributes(HTMLAttributes, {
        "data-callout": "",
        class: `rich-callout ${EDITOR_TONES[variant] ?? EDITOR_TONES.info}`,
      }),
      0,
    ];
  },

  addCommands() {
    return {
      toggleCallout:
        (variant) =>
        ({ commands, editor }) => {
          if (editor.isActive(this.name, { variant })) {
            return commands.lift(this.name);
          }
          if (editor.isActive(this.name)) {
            return commands.updateAttributes(this.name, { variant });
          }
          return commands.wrapIn(this.name, { variant });
        },
    };
  },
});
