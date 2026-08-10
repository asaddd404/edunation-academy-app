// Both auth forms show a fixed "+7" prefix next to a digits-only input,
// rather than pre-filling "+7" as editable text in the field itself --
// that earlier approach let a caret land after the prefix and then a full
// number typed (or pasted) out of habit, "+77001234567", produced
// "+7+77001234567", which the backend correctly (but unhelpfully) rejected.
// Keeping the "+7" out of the editable value avoids that collision, but
// people still habitually type or paste their own leading country code
// ("+7"/"8") into a field that already implies it. Sanitize that on the
// way in rather than truncating blindly: an 11-digit result that starts
// with 7 or 8 almost certainly carries a redundant leading digit, so drop
// that one digit instead of the real number's last one.
export function sanitizeLocalPhoneDigits(raw: string): string {
  let digits = raw.replace(/\D/g, "");
  if (digits.length === 11 && (digits.startsWith("7") || digits.startsWith("8"))) {
    digits = digits.slice(1);
  }
  return digits.slice(0, 10);
}

export function localDigitsToPhone(local: string): string {
  return "+7" + sanitizeLocalPhoneDigits(local);
}
