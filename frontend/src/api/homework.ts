import http from "@/api/http";
import type { HomeworkListFilter, HomeworkSubmission } from "@/types";

export function getMyHomework(lessonId: number) {
  return http.get<HomeworkSubmission | null>(`/lessons/${lessonId}/homework`).then((r) => r.data);
}

export function submitHomework(lessonId: number, textAnswer: string, file: File | null) {
  const form = new FormData();
  if (textAnswer) form.append("text_answer", textAnswer);
  if (file) form.append("file", file);
  return http
    .post<HomeworkSubmission>(`/lessons/${lessonId}/homework`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    .then((r) => r.data);
}

export function listPendingHomework() {
  return http.get<HomeworkSubmission[]>("/teacher/homework/pending").then((r) => r.data);
}

/** Homework in the teacher's courses, by status and optionally one student. */
export function listHomework(status: HomeworkListFilter, studentId?: number | null) {
  return http
    .get<HomeworkSubmission[]>("/teacher/homework", { params: { status, student_id: studentId ?? undefined } })
    .then((r) => r.data);
}

export function reviewHomework(
  submissionId: number,
  status: "accepted" | "revision_requested",
  feedback?: string,
  grade?: number | null,
) {
  return http
    .post<HomeworkSubmission>(`/teacher/homework/${submissionId}/review`, { status, feedback, grade: grade ?? null })
    .then((r) => r.data);
}

/**
 * The attachment as a blob: URL. Plain <a href>/<img src> can't carry the
 * Authorization header the backend requires, so the file is fetched through
 * the authenticated client. `inline` asks for the previewable form (image /
 * PDF with its real type); the caller revokes the URL when done.
 */
export async function fetchHomeworkFileUrl(submissionId: number, inline = false): Promise<string> {
  const response = await http.get(`/homework/${submissionId}/file`, {
    responseType: "blob",
    params: inline ? { inline: 1 } : undefined,
  });
  return URL.createObjectURL(response.data as Blob);
}

export async function downloadHomeworkFile(submissionId: number, suggestedName: string) {
  const blobUrl = await fetchHomeworkFileUrl(submissionId);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = suggestedName;
  link.click();
  URL.revokeObjectURL(blobUrl);
}
