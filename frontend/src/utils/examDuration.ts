import { pluralRu } from "@/utils/subjectTheme";

/** Full ЕНТ is 5 subjects in 240 minutes -- 48 minutes per subject either way. */
export const ENT_MINUTES_PER_SUBJECT = 48;
export const ENT_FULL_SUBJECT_COUNT = 5;

/** Selecting more than the full ЕНТ's 5 subjects still caps at 240 minutes. */
export function calcExamDurationMinutes(selectedSubjectCount: number): number {
  return Math.min(Math.max(selectedSubjectCount, 0), ENT_FULL_SUBJECT_COUNT) * ENT_MINUTES_PER_SUBJECT;
}

/** e.g. 96 -> "96 минут (1 час 36 минут)", 48 -> "48 минут". */
export function formatExamDuration(totalMinutes: number): string {
  const base = `${totalMinutes} ${pluralRu(totalMinutes, ["минута", "минуты", "минут"])}`;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) return base;
  return `${base} (${hours} ${pluralRu(hours, ["час", "часа", "часов"])} ${minutes} ${pluralRu(minutes, ["минута", "минуты", "минут"])})`;
}
