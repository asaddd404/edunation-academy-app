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
  <div class="relative isolate flex min-h-[70vh] items-center justify-center px-4 py-16">
    <div class="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      <div class="glow-blob left-1/2 top-1/3 h-[26rem] w-[26rem] -translate-x-1/2 animate-drift" />
      <div
        class="glow-blob bottom-8 right-1/4 h-64 w-64 animate-drift"
        style="animation-delay: -8s; background: radial-gradient(circle, hsl(330 81% 60% / 0.45), transparent 70%)"
      />
    </div>

    <div class="max-w-lg text-center">
      <p class="animate-fade-up text-[6rem] font-bold leading-none tracking-tighter sm:text-[9rem]">
        <span class="text-gradient-brand">404</span>
      </p>

      <h1 class="mt-2 animate-fade-up text-2xl font-bold tracking-tight sm:text-3xl" style="animation-delay: 80ms">
        Такой страницы нет
      </h1>

      <p class="mt-4 animate-fade-up text-fg/60" style="animation-delay: 160ms">
        Возможно, ссылка устарела или в адресе опечатка. Проверь адрес или вернись к учёбе.
      </p>

      <div class="mt-8 flex animate-fade-up flex-wrap justify-center gap-3" style="animation-delay: 240ms">
        <router-link
          :to="homeLink.to"
          class="inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 px-6 py-3.5 text-sm font-medium text-white shadow-lg shadow-indigo-500/25 transition-all duration-200 hover:scale-[1.02] hover:shadow-indigo-500/40 active:scale-[0.98]"
        >
          {{ homeLink.label }}
          <span aria-hidden="true">→</span>
        </router-link>
        <button
          type="button"
          class="inline-flex items-center justify-center rounded-xl border border-fg/20 px-6 py-3.5 text-sm font-medium text-fg transition-colors duration-200 hover:bg-fg/5"
          @click="goBack"
        >
          Назад
        </button>
      </div>
    </div>
  </div>
</template>
