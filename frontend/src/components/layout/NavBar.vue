<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();

const links = computed(() => {
  if (auth.role === "student") {
    return [
      { to: "/catalog", label: "Каталог" },
      { to: "/my-applications", label: "Мои заявки" },
      { to: "/ent", label: "ЕНТ-тренажёр" },
    ];
  }
  if (auth.role === "teacher") {
    return [
      { to: "/teacher", label: "Заявки" },
      { to: "/teacher/categories", label: "Мои категории" },
      { to: "/teacher/homework", label: "Домашки" },
      { to: "/teacher/ent", label: "Банк ЕНТ" },
    ];
  }
  if (auth.role === "admin") {
    return [
      { to: "/admin", label: "Админ-панель" },
      { to: "/teacher/ent", label: "Банк ЕНТ" },
    ];
  }
  return [];
});

function handleLogout() {
  auth.logout();
  router.push("/login");
}
</script>

<template>
  <header class="sticky top-0 z-10 border-b border-fg/10 bg-bg/95 backdrop-blur">
    <div class="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-3">
      <span class="text-lg font-semibold tracking-tight">Edunation Academy</span>
      <nav v-if="auth.isAuthenticated" class="flex items-center gap-4 text-sm">
        <router-link
          v-for="link in links"
          :key="link.to"
          :to="link.to"
          class="text-fg/70 hover:text-fg"
          active-class="text-accent font-medium"
        >
          {{ link.label }}
        </router-link>
        <button class="text-fg/50 hover:text-fg" @click="handleLogout">Выйти</button>
      </nav>
    </div>
  </header>
</template>
