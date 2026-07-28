import http from "@/api/http";
import type { HomeworkSubmission } from "@/types";

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

export function reviewHomework(submissionId: number, status: "accepted" | "revision_requested", feedback?: string) {
  return http
    .post<HomeworkSubmission>(`/teacher/homework/${submissionId}/review`, { status, feedback })
    .then((r) => r.data);
}

export async function downloadHomeworkFile(submissionId: number, suggestedName: string) {
  // Plain <a href> can't carry the Authorization header the backend requires,
  // so the file has to be fetched through the authenticated axios client and
  // saved via a blob URL instead of linking directly to the API endpoint.
  const response = await http.get(`/homework/${submissionId}/file`, { responseType: "blob" });
  const blobUrl = URL.createObjectURL(response.data as Blob);
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = suggestedName;
  link.click();
  URL.revokeObjectURL(blobUrl);
}
