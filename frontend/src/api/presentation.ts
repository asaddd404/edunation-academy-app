import http from "@/api/http";
import type { LessonTeacher } from "@/types";

export interface PresentationLink {
  /** "office": PowerPoint, framed in Microsoft's viewer. "pdf": shown by the browser. */
  kind: "office" | "pdf";
  /** Microsoft's Office viewer, already pointing at a short-lived file link. */
  embed_url: string | null;
  /** API-relative short-lived link to the PDF. */
  file_path: string | null;
}

/** The viewer's own limit; the server enforces it too. */
export const MAX_PRESENTATION_BYTES = 10 * 1024 * 1024;

/** What the server accepts (see PRESENTATION_MEDIA_TYPES in app/core/storage.py). */
export const PRESENTATION_EXTENSIONS = [".pptx", ".ppsx", ".pdf"] as const;
export const PRESENTATION_ACCEPT = [
  ...PRESENTATION_EXTENSIONS,
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "application/vnd.openxmlformats-officedocument.presentationml.slideshow",
  "application/pdf",
].join(",");

export function isPdfPresentation(name: string | null | undefined): boolean {
  return !!name && name.toLowerCase().endsWith(".pdf");
}

/** The PDF itself, for the browser's PDF viewer. */
export function fetchPresentationPdf(filePath: string) {
  return http.get<Blob>(filePath, { responseType: "blob" }).then((r) => new Blob([r.data], { type: "application/pdf" }));
}

export function uploadLessonPresentation(lessonId: number, file: File, onProgress?: (percent: number) => void) {
  const formData = new FormData();
  formData.append("file", file);
  return http
    .post<LessonTeacher>(`/teacher/lessons/${lessonId}/presentation`, formData, {
      onUploadProgress: (event) => {
        if (onProgress && event.total) onProgress(Math.round((event.loaded / event.total) * 100));
      },
    })
    .then((r) => r.data);
}

export function deleteLessonPresentation(lessonId: number) {
  return http.delete<LessonTeacher>(`/teacher/lessons/${lessonId}/presentation`).then((r) => r.data);
}

export function getStudentPresentationLink(lessonId: number) {
  return http.post<PresentationLink>(`/lessons/${lessonId}/presentation/link`).then((r) => r.data);
}

export function getTeacherPresentationLink(lessonId: number) {
  return http.post<PresentationLink>(`/teacher/lessons/${lessonId}/presentation/link`).then((r) => r.data);
}

export function formatFileSize(bytes: number | null | undefined): string {
  if (!bytes) return "";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} МБ`;
}
