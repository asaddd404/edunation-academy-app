export interface GlossaryTextSegment {
  type: "text";
  value: string;
}

export interface GlossaryTermSegment {
  type: "term";
  term: string;
  explanation: string;
}

export type GlossarySegment = GlossaryTextSegment | GlossaryTermSegment;

// [Термин|Объяснение] -- explanation can't itself contain `]`, term can't
// contain `|` or `]`; that's the whole grammar, no escaping supported.
const GLOSSARY_PATTERN = /\[([^|\]]+)\|([^\]]+)\]/g;

export function parseGlossary(raw: string): GlossarySegment[] {
  const segments: GlossarySegment[] = [];
  let lastIndex = 0;

  for (const match of raw.matchAll(GLOSSARY_PATTERN)) {
    const start = match.index ?? 0;
    if (start > lastIndex) segments.push({ type: "text", value: raw.slice(lastIndex, start) });
    segments.push({ type: "term", term: match[1], explanation: match[2] });
    lastIndex = start + match[0].length;
  }
  if (lastIndex < raw.length) segments.push({ type: "text", value: raw.slice(lastIndex) });

  return segments;
}

/** Every glossary term currently present in a draft, in order, de-duplicated by term text. */
export function extractGlossaryTerms(raw: string): GlossaryTermSegment[] {
  const seen = new Set<string>();
  const terms: GlossaryTermSegment[] = [];
  for (const segment of parseGlossary(raw)) {
    if (segment.type !== "term" || seen.has(segment.term)) continue;
    seen.add(segment.term);
    terms.push(segment);
  }
  return terms;
}
