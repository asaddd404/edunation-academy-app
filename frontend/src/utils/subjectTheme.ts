// Shared "which gradient/emoji represents this subject" + small RU text
// helpers, used by CatalogView (course subjects) and EntStartView (ENT
// subjects) so both pick the same visual identity for e.g. "Химия".

const SUBJECT_THEMES: { match: RegExp; icon: string; gradient: string }[] = [
  { match: /матем|алгебр|геометр/i, icon: "📐", gradient: "from-sky-500 to-cyan-400" },
  { match: /хими/i, icon: "🧪", gradient: "from-fuchsia-500 to-pink-500" },
  { match: /физик/i, icon: "⚛️", gradient: "from-blue-600 to-indigo-500" },
  { match: /биолог/i, icon: "🧬", gradient: "from-emerald-500 to-lime-400" },
  { match: /истори/i, icon: "📜", gradient: "from-amber-500 to-orange-500" },
  { match: /географ/i, icon: "🌍", gradient: "from-teal-500 to-emerald-400" },
  { match: /информат|программ/i, icon: "💻", gradient: "from-indigo-600 to-blue-500" },
  { match: /англ/i, icon: "🔤", gradient: "from-violet-500 to-purple-500" },
  { match: /рус|литератур/i, icon: "📚", gradient: "from-rose-500 to-pink-400" },
  { match: /казах/i, icon: "🌾", gradient: "from-teal-600 to-cyan-500" },
];

const FALLBACK_GRADIENTS = [
  "from-indigo-500 to-purple-500",
  "from-cyan-500 to-blue-500",
  "from-pink-500 to-rose-500",
  "from-amber-500 to-red-500",
];

export function subjectTheme(name: string, id: number): { icon: string; gradient: string } {
  const found = SUBJECT_THEMES.find((t) => t.match.test(name));
  if (found) return found;
  return { icon: "📘", gradient: FALLBACK_GRADIENTS[id % FALLBACK_GRADIENTS.length] };
}

export function capitalize(text: string): string {
  return text.length ? text[0].toUpperCase() + text.slice(1) : text;
}

export function pluralRu(n: number, forms: [string, string, string]): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return forms[2];
  if (mod10 === 1) return forms[0];
  if (mod10 >= 2 && mod10 <= 4) return forms[1];
  return forms[2];
}
