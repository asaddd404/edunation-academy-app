/**
 * `Lesson.description` / `Lesson.homework_assignment` hold either a TipTap
 * JSON document (rich content written by the new editor) or legacy plain
 * text, possibly carrying `[Термин|Объяснение]` glossary markup. The column
 * is plain TEXT either way -- no migration was needed -- so the format is
 * sniffed at render time.
 */

import { parseGlossary } from "@/utils/glossary";

export interface RichMark {
  type: string;
  attrs?: Record<string, unknown>;
}

export interface RichNode {
  type: string;
  attrs?: Record<string, unknown>;
  content?: RichNode[];
  marks?: RichMark[];
  text?: string;
}

export type ParsedContent =
  | { kind: "rich"; doc: RichNode }
  | { kind: "plain"; text: string }
  | { kind: "empty" };

export function parseRichContent(raw: string | null | undefined): ParsedContent {
  if (!raw || !raw.trim()) return { kind: "empty" };

  // Cheap guard so ordinary prose never reaches JSON.parse just to throw.
  if (raw.trimStart().startsWith("{")) {
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && parsed.type === "doc") {
        return { kind: "rich", doc: parsed as RichNode };
      }
    } catch {
      // Not JSON after all -- fall through and treat it as prose.
    }
  }
  return { kind: "plain", text: raw };
}

/**
 * Lifts legacy plain text into a TipTap document, turning any
 * `[Термин|Объяснение]` markup into real glossaryTerm marks.
 *
 * This conversion is what stops the old syntax from silently breaking: the
 * rich renderer does not interpret brackets, so a teacher who opens an old
 * lesson in the new editor and saves would otherwise leave students staring
 * at literal `[...]` text where a hint used to be.
 */
export function plainTextToDoc(text: string): RichNode {
  const paragraphs = text.split("\n").map((line) => {
    const content: RichNode[] = parseGlossary(line).map((segment) =>
      segment.type === "text"
        ? { type: "text", text: segment.value }
        : {
            type: "text",
            text: segment.term,
            marks: [{ type: "glossaryTerm", attrs: { explanation: segment.explanation } }],
          },
    );
    // TipTap rejects a text node with an empty string, so a blank line has to
    // become a paragraph with no content at all.
    return { type: "paragraph", ...(content.length ? { content } : {}) };
  });

  return { type: "doc", content: paragraphs };
}

/** A TipTap doc can be "non-empty" structurally while rendering to nothing
 * (one empty paragraph is what a cleared editor emits). Used to decide
 * whether to show the description block at all. */
export function isRichDocEmpty(doc: RichNode): boolean {
  const hasVisible = (node: RichNode): boolean => {
    if (node.type === "text") return Boolean(node.text && node.text.trim());
    // Leaf nodes that carry meaning without text of their own.
    if (node.type === "image" || node.type === "horizontalRule" || node.type === "table") return true;
    return (node.content ?? []).some(hasVisible);
  };
  return !hasVisible(doc);
}
