import http from "@/api/http";
import type { LessonTeacher } from "@/types";

interface VideoTicket {
  playback_path: string;
}

export function uploadLessonVideo(lessonId: number, file: File, onProgress?: (percent: number) => void) {
  const formData = new FormData();
  formData.append("file", file);
  return http
    .post<LessonTeacher>(`/teacher/lessons/${lessonId}/video`, formData, {
      onUploadProgress: (event) => {
        if (onProgress && event.total) onProgress(Math.round((event.loaded / event.total) * 100));
      },
    })
    .then((r) => r.data);
}

export function deleteLessonVideo(lessonId: number) {
  return http.delete<LessonTeacher>(`/teacher/lessons/${lessonId}/video`).then((r) => r.data);
}

export function getTeacherLesson(lessonId: number) {
  return http.get<LessonTeacher>(`/teacher/lessons/${lessonId}`).then((r) => r.data);
}

export function getTeacherVideoTicket(lessonId: number) {
  return http.post<VideoTicket>(`/teacher/lessons/${lessonId}/video/ticket`, null, { withCredentials: true }).then((r) => r.data);
}

export function getStudentVideoTicket(lessonId: number) {
  return http.post<VideoTicket>(`/lessons/${lessonId}/video/ticket`, null, { withCredentials: true }).then((r) => r.data);
}
