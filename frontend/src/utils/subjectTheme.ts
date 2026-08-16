// Small RU text helpers shared across catalog and ЕНТ screens.
//
// This file used to also map a subject name to an emoji + gradient. The
// emoji moved into components/ui/SubjectIcon.vue (Lucide, so it inherits
// currentColor and renders identically on every OS) and the gradients had
// no callers left, so only the language helpers remain.

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
