export type ActivityLevel = "low" | "medium" | "high";

const LOW_MAX_SECONDS = 1800;
const MEDIUM_MAX_SECONDS = 3600;

export function activityLevel(totalSeconds: number): ActivityLevel {
  if (totalSeconds < LOW_MAX_SECONDS) return "low";
  if (totalSeconds < MEDIUM_MAX_SECONDS) return "medium";
  return "high";
}

// "ч"/"м" don't decline by count in Russian ("5 ч 30 м"), so no plural forms needed.
export function formatActivityDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return hours > 0 ? `${hours} ч ${remainingMinutes} м` : `${minutes} м`;
}
