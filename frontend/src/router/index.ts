import { createRouter, createWebHistory } from "vue-router";

import { useAuthStore } from "@/stores/auth";
import type { Role } from "@/types";

const HOME_BY_ROLE: Record<Role, string> = {
  student: "/catalog",
  teacher: "/teacher",
  admin: "/admin",
};

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/catalog" },
    {
      path: "/register",
      name: "register",
      component: () => import("@/views/auth/RegisterView.vue"),
      meta: { guestOnly: true },
    },
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/auth/LoginView.vue"),
      meta: { guestOnly: true },
    },
    {
      path: "/catalog",
      name: "catalog",
      component: () => import("@/views/student/CatalogView.vue"),
      meta: { roles: ["student"] as Role[] },
    },
    {
      path: "/my-applications",
      name: "my-applications",
      component: () => import("@/views/student/MyApplicationsView.vue"),
      meta: { roles: ["student"] as Role[] },
    },
    {
      path: "/categories/:id",
      name: "category-content",
      component: () => import("@/views/student/CategoryContentView.vue"),
      meta: { roles: ["student"] as Role[] },
    },
    {
      path: "/lessons/:id",
      name: "lesson",
      component: () => import("@/views/student/LessonView.vue"),
      meta: { roles: ["student"] as Role[] },
    },
    {
      path: "/teacher",
      name: "teacher",
      component: () => import("@/views/teacher/TeacherDashboardView.vue"),
      meta: { roles: ["teacher"] as Role[] },
    },
    {
      path: "/teacher/categories",
      name: "teacher-categories",
      component: () => import("@/views/teacher/TeacherCategoriesView.vue"),
      meta: { roles: ["teacher"] as Role[] },
    },
    {
      path: "/teacher/categories/:id",
      name: "teacher-course-builder",
      component: () => import("@/views/teacher/CourseBuilderView.vue"),
      meta: { roles: ["teacher"] as Role[] },
    },
    {
      path: "/teacher/homework",
      name: "teacher-homework",
      component: () => import("@/views/teacher/TeacherHomeworkView.vue"),
      meta: { roles: ["teacher"] as Role[] },
    },
    {
      path: "/admin",
      name: "admin",
      component: () => import("@/views/admin/AdminDashboardView.vue"),
      meta: { roles: ["admin"] as Role[] },
    },
  ],
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  await auth.initialize();

  const roles = to.meta.roles as Role[] | undefined;
  const guestOnly = to.meta.guestOnly as boolean | undefined;

  if (guestOnly && auth.isAuthenticated) {
    return HOME_BY_ROLE[auth.role as Role];
  }
  if (roles && !auth.isAuthenticated) {
    return { path: "/login", query: { redirect: to.fullPath } };
  }
  if (roles && auth.role && !roles.includes(auth.role)) {
    return HOME_BY_ROLE[auth.role];
  }
  return true;
});

export default router;
