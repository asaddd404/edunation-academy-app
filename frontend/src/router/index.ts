import { createRouter, createWebHistory } from "vue-router";

import { useAuthStore } from "@/stores/auth";
import type { Role } from "@/types";

declare module "vue-router" {
  interface RouteMeta {
    /** Roles allowed to open the route. Absent => public. */
    roles?: Role[];
    /** Authenticated users get bounced to their role home. */
    guestOnly?: boolean;
  }
}

// Exported so views that need to send a signed-in user "home" (post-login
// redirect, the 404 page's back link) share this one mapping.
export const HOME_BY_ROLE: Record<Role, string> = {
  student: "/catalog",
  teacher: "/teacher",
  admin: "/admin",
};

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      // Deliberately not guestOnly: the navbar brand link points here for
      // every visitor, signed in or not, so it has to stay reachable
      // instead of bouncing an authenticated user back to their dashboard.
      path: "/",
      name: "landing",
      component: () => import("@/views/public/LandingView.vue"),
    },
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
      path: "/forgot-password",
      name: "forgot-password",
      component: () => import("@/views/auth/ForgotPasswordView.vue"),
      meta: { guestOnly: true },
    },
    {
      path: "/catalog",
      name: "catalog",
      component: () => import("@/views/student/CatalogView.vue"),
      meta: { roles: ["student"] },
    },
    {
      path: "/my-applications",
      name: "my-applications",
      component: () => import("@/views/student/MyApplicationsView.vue"),
      meta: { roles: ["student"] },
    },
    {
      // Retired in favor of the Miller Columns catalog shell -- kept as a
      // redirect so old links/bookmarks into a specific category still land
      // somewhere useful.
      path: "/categories/:id",
      redirect: (to) => ({ path: "/catalog", query: { category: to.params.id } }),
    },
    {
      path: "/lessons/:id",
      name: "lesson",
      component: () => import("@/views/student/LessonView.vue"),
      meta: { roles: ["student"] },
    },
    {
      path: "/sections/:id/test",
      name: "section-test",
      component: () => import("@/views/student/SectionTestView.vue"),
      meta: { roles: ["student"] },
    },
    {
      path: "/ent",
      name: "ent-start",
      component: () => import("@/views/student/EntStartView.vue"),
      meta: { roles: ["student"] },
    },
    {
      path: "/ent/leaderboard",
      name: "ent-leaderboard",
      component: () => import("@/views/student/EntLeaderboardView.vue"),
      meta: { roles: ["student"] },
    },
    {
      path: "/ent/:id",
      name: "ent-simulation",
      component: () => import("@/views/student/EntSimulationView.vue"),
      meta: { roles: ["student"] },
    },
    {
      path: "/teacher",
      name: "teacher",
      component: () => import("@/views/teacher/TeacherDashboardView.vue"),
      meta: { roles: ["teacher", "admin"] },
    },
    {
      path: "/teacher/categories",
      name: "teacher-categories",
      component: () => import("@/views/teacher/TeacherCategoriesView.vue"),
      meta: { roles: ["teacher", "admin"] },
    },
    {
      path: "/teacher/categories/:id",
      name: "teacher-course-builder",
      component: () => import("@/views/teacher/CourseBuilderView.vue"),
      meta: { roles: ["teacher", "admin"] },
    },
    {
      path: "/teacher/homework",
      name: "teacher-homework",
      component: () => import("@/views/teacher/TeacherHomeworkView.vue"),
      meta: { roles: ["teacher", "admin"] },
    },
    {
      path: "/teacher/ent",
      name: "teacher-ent-bank",
      component: () => import("@/views/teacher/TeacherEntBankView.vue"),
      meta: { roles: ["teacher", "admin"] },
    },
    {
      path: "/admin",
      name: "admin",
      component: () => import("@/views/admin/AdminDashboardView.vue"),
      meta: { roles: ["admin"] },
    },
    {
      path: "/profile",
      name: "profile",
      component: () => import("@/views/ProfileView.vue"),
      meta: { roles: ["student", "teacher", "admin"] },
    },
    {
      // Catch-all must stay last: anything unmatched above renders the 404.
      path: "/:pathMatch(.*)*",
      name: "not-found",
      component: () => import("@/views/NotFoundView.vue"),
    },
  ],
  scrollBehavior(_to, _from, savedPosition) {
    return savedPosition ?? { top: 0 };
  },
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  await auth.initialize();

  const { roles, guestOnly } = to.meta;

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
