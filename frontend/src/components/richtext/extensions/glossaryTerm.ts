import { Mark, mergeAttributes } from "@tiptap/core";

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    glossaryTerm: {
      setGlossaryTerm: (explanation: string) => ReturnType;
      unsetGlossaryTerm: () => ReturnType;
    };
  }
}

/**
 * The rich-text equivalent of the legacy `[Термин|Объяснение]` syntax: the
 * explanation rides along as a mark attribute instead of being typed inline,
 * so the teacher selects a word and fills in a field rather than remembering
 * bracket syntax. Rendered for students by RichTextSpan via GlossaryTooltip.
 */
export const GlossaryTerm = Mark.create({
  name: "glossaryTerm",
  // A term is one self-contained annotation -- letting it merge with an
  // adjacent one would silently join two different explanations.
  inclusive: false,

  addAttributes() {
    return {
      explanation: {
        default: "",
        parseHTML: (element) => element.getAttribute("data-explanation") ?? "",
        renderHTML: (attributes) => ({ "data-explanation": attributes.explanation }),
      },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-glossary-term]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(HTMLAttributes, {
        "data-glossary-term": "",
        class: "border-b border-dashed border-moss font-medium text-moss",
      }),
      0,
    ];
  },

  addCommands() {
    return {
      setGlossaryTerm:
        (explanation) =>
        ({ commands }) =>
          commands.setMark(this.name, { explanation }),
      unsetGlossaryTerm:
        () =>
        ({ commands }) =>
          commands.unsetMark(this.name),
    };
  },
});
