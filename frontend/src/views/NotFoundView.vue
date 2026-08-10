<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();

// Send the visitor somewhere that actually exists for them: their role's home
// when signed in, the public landing otherwise.
const homeLink = computed(() => {
  if (!auth.isAuthenticated) return { to: "/", label: "На главную" };
  if (auth.role === "teacher") return { to: "/teacher", label: "К заявкам" };
  if (auth.role === "admin") return { to: "/admin", label: "В админ-панель" };
  return { to: "/catalog", label: "В каталог" };
});

function goBack() {
  if (window.history.length > 1) router.back();
  else router.push(homeLink.value.to);
}
</script>

<template>
  <div class="flex min-h-[60vh] items-center justify-center px-4 py-16">
    <div class="max-w-lg text-center">
      <p class="motion-safe:animate-fade-up font-display text-[6rem] font-bold leading-none tracking-tighter text-ink sm:text-[9rem]">
        404
      </p>

      <h1
        class="mt-2 motion-safe:animate-fade-up font-display text-display-lg text-ink"
        style="animation-delay: 80ms"
      >
        Такой страницы нет
      </h1>

      <p class="mt-4 motion-safe:animate-fade-up text-ink-2" style="animation-delay: 160ms">
        Возможно, ссылка устарела или в адресе опечатка. Проверь адрес или вернись к учёбе.
      </p>

      <div class="mt-8 flex motion-safe:animate-fade-up flex-wrap justify-center gap-3" style="animation-delay: 240ms">
        <router-link :to="homeLink.to" class="btn-primary">
          {{ homeLink.label }}
          <span aria-hidden="true">→</span>
        </router-link>
        <button type="button" class="btn-ghost" @click="goBack">Назад</button>
      </div>
    </div>
  </div>
</template>
