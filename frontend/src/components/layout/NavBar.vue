<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";
import { useNotificationsStore } from "@/stores/notifications";
import { useThemeStore } from "@/stores/theme";

const auth = useAuthStore();
const router = useRouter();
const route = useRoute();
const notifications = useNotificationsStore();
const theme = useThemeStore();

// Match AppShell's container so the header lines up with the page content.
const containerWidth = computed(() => (route.meta.layout === "full" ? "max-w-6xl" : "max-w-3xl"));

const links = computed(() => {
  if (auth.role === "student") {
    return [
      { to: "/catalog", label: "Каталог" },
      { to: "/my-applications", label: "Мои заявки" },
      { to: "/ent", label: "ЕНТ-тренажёр" },
      { to: "/profile", label: "Профиль" },
    ];
  }
  if (auth.role === "teacher") {
    return [
      { to: "/teacher", label: "Заявки" },
      { to: "/teacher/categories", label: "Мои категории" },
      { to: "/teacher/homework", label: "Домашки" },
      { to: "/teacher/ent", label: "Банк ЕНТ" },
      { to: "/profile", label: "Профиль" },
    ];
  }
  if (auth.role === "admin") {
    return [
      { to: "/admin", label: "Админ-панель" },
      { to: "/teacher", label: "Заявки" },
      { to: "/teacher/categories", label: "Мои категории" },
      { to: "/teacher/homework", label: "Домашки" },
      { to: "/teacher/ent", label: "Банк ЕНТ" },
      { to: "/profile", label: "Профиль" },
    ];
  }
  return [];
});

const bellRoot = ref<HTMLElement | null>(null);
const dropdownOpen = ref(false);
const mobileMenuOpen = ref(false);

function closeMobileMenu() {
  mobileMenuOpen.value = false;
}

async function toggleDropdown() {
  dropdownOpen.value = !dropdownOpen.value;
  if (dropdownOpen.value) await notifications.fetchList();
}

function handleClickOutside(event: MouseEvent) {
  if (bellRoot.value && !bellRoot.value.contains(event.target as Node)) dropdownOpen.value = false;
}

async function handleNotificationClick(notification: { id: number; link: string | null; is_read: boolean }) {
  await notifications.markRead(notification.id);
  dropdownOpen.value = false;
  if (notification.link) router.push(notification.link);
}

async function handleDeleteNotification(event: MouseEvent, id: number) {
  event.stopPropagation();
  await notifications.remove(id);
}

async function handleClearAll() {
  await notifications.clearAll();
}

watch(
  () => auth.isAuthenticated,
  (isAuthenticated) => {
    if (isAuthenticated) notifications.startPolling();
    else notifications.stopPolling();
  },
  { immediate: true },
);

watch(() => router.currentRoute.value.fullPath, closeMobileMenu);

onMounted(() => document.addEventListener("click", handleClickOutside));
onBeforeUnmount(() => document.removeEventListener("click", handleClickOutside));

function handleLogout() {
  auth.logout();
  router.push("/login");
}
</script>

<template>
  <header class="sticky top-0 z-20 border-b border-fg/10 bg-bg/95 backdrop-blur">
    <div class="mx-auto flex items-center justify-between gap-3 px-4 py-3" :class="containerWidth">
      <router-link
        to="/"
        class="text-base font-semibold tracking-tight transition-opacity hover:opacity-70 sm:text-lg"
      >
        Edunation Academy
      </router-link>

      <div class="flex items-center gap-2">
        <nav v-if="auth.isAuthenticated" class="hidden items-center gap-4 text-sm md:flex">
          <router-link
            v-for="link in links"
            :key="link.to"
            :to="link.to"
            class="text-fg/70 hover:text-fg"
            active-class="text-accent font-medium"
          >
            {{ link.label }}
          </router-link>
        </nav>

        <button
          class="relative flex h-8 w-8 items-center justify-center overflow-hidden rounded-full text-fg/70 hover:bg-fg/10 hover:text-fg"
          :aria-label="theme.theme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему'"
          @click="theme.toggle"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            class="absolute h-5 w-5 transition-all duration-300"
            :class="theme.theme === 'dark' ? 'rotate-0 scale-100 opacity-100' : 'rotate-90 scale-50 opacity-0'"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.4-6.4l-.7.7M6.3 17.7l-.7.7m12.8 0l-.7-.7M6.3 6.3l-.7-.7" />
            <circle cx="12" cy="12" r="4" />
          </svg>
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
            class="absolute h-5 w-5 transition-all duration-300"
            :class="theme.theme === 'dark' ? '-rotate-90 scale-50 opacity-0' : 'rotate-0 scale-100 opacity-100'"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z"
            />
          </svg>
        </button>

        <div v-if="!auth.isAuthenticated" class="flex items-center gap-1.5 sm:gap-2">
          <router-link
            to="/login"
            class="rounded-lg px-2.5 py-1.5 text-sm text-fg/70 transition-colors duration-200 hover:bg-fg/5 hover:text-fg sm:px-3"
          >
            Войти
          </router-link>
          <router-link
            to="/register"
            class="rounded-lg bg-gradient-to-r from-indigo-600 to-violet-600 px-3 py-1.5 text-sm font-medium text-white shadow-md shadow-indigo-500/20 transition-all duration-200 hover:scale-[1.03] hover:shadow-indigo-500/40 active:scale-95 sm:px-4"
          >
            Регистрация
          </router-link>
        </div>

        <button
          v-if="auth.isAuthenticated"
          class="flex h-8 w-8 items-center justify-center rounded-lg text-fg/70 hover:bg-fg/10 md:hidden"
          aria-label="Меню"
          @click="mobileMenuOpen = !mobileMenuOpen"
        >
          <svg v-if="!mobileMenuOpen" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="h-5 w-5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 7h16M4 12h16M4 17h16" />
          </svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="h-5 w-5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>

        <div v-if="auth.isAuthenticated" ref="bellRoot" class="relative">
          <button
            class="relative flex h-8 w-8 items-center justify-center rounded-full text-fg/70 hover:bg-fg/10 hover:text-fg"
            aria-label="Уведомления"
            @click.stop="toggleDropdown"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="h-5 w-5">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15 17h5l-1.4-1.4A2 2 0 0 1 18 14.2V11a6 6 0 1 0-12 0v3.2a2 2 0 0 1-.6 1.4L4 17h5m6 0a3 3 0 1 1-6 0m6 0H9" />
            </svg>
            <span
              v-if="notifications.unreadCount > 0"
              class="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium text-white"
            >
              {{ notifications.unreadCount > 9 ? "9+" : notifications.unreadCount }}
            </span>
          </button>

          <div
            v-if="dropdownOpen"
            class="absolute right-0 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-fg/10 bg-bg shadow-lg"
          >
            <div class="flex items-center justify-between border-b border-fg/10 px-3 py-2">
              <span class="text-sm font-medium">Уведомления</span>
              <div class="flex items-center gap-3">
                <button
                  v-if="notifications.items.some((n) => !n.is_read)"
                  class="text-xs text-accent underline underline-offset-2 hover:opacity-70"
                  @click="notifications.markAllRead"
                >
                  Прочитать все
                </button>
                <button
                  v-if="notifications.items.length"
                  class="text-xs text-fg/50 hover:text-red-500 hover:underline"
                  @click="handleClearAll"
                >
                  Очистить всё
                </button>
              </div>
            </div>
            <ul class="max-h-96 overflow-y-auto">
              <li v-if="notifications.items.length === 0" class="px-3 py-6 text-center text-sm text-fg/50">
                Пока нет уведомлений
              </li>
              <li
                v-for="notification in notifications.items"
                :key="notification.id"
                class="group flex cursor-pointer items-start gap-2 border-b border-fg/5 px-3 py-3 text-sm last:border-b-0 hover:bg-fg/5"
                :class="{ 'bg-accent/5': !notification.is_read }"
                @click="handleNotificationClick(notification)"
              >
                <div class="flex-1">
                  <p :class="notification.is_read ? 'text-fg/60' : 'font-medium text-fg'">{{ notification.message }}</p>
                  <p class="mt-1 text-xs text-fg/40">{{ new Date(notification.created_at).toLocaleString("ru-RU") }}</p>
                </div>
                <button
                  class="shrink-0 rounded p-1 text-fg/30 opacity-0 hover:text-red-500 group-hover:opacity-100"
                  aria-label="Удалить уведомление"
                  @click="handleDeleteNotification($event, notification.id)"
                >
                  ✕
                </button>
              </li>
            </ul>
            <div v-if="notifications.hasMore" class="border-t border-fg/10 p-2">
              <button
                class="w-full rounded-lg px-3 py-2 text-center text-xs font-medium text-fg/60 hover:bg-fg/5 hover:text-fg disabled:opacity-50"
                :disabled="notifications.loadingMore"
                @click="notifications.loadMore"
              >
                {{ notifications.loadingMore ? "Загрузка…" : "Показать ещё" }}
              </button>
            </div>
          </div>
        </div>

        <button
          v-if="auth.isAuthenticated"
          class="hidden text-sm text-fg/50 hover:text-fg md:inline-block"
          @click="handleLogout"
        >
          Выйти
        </button>
      </div>
    </div>

    <nav
      v-if="auth.isAuthenticated && mobileMenuOpen"
      class="flex flex-col gap-1 border-t border-fg/10 px-4 py-3 text-sm md:hidden"
    >
      <router-link
        v-for="link in links"
        :key="link.to"
        :to="link.to"
        class="rounded-lg px-3 py-2.5 text-fg/70 hover:bg-fg/5"
        active-class="bg-fg/5 text-accent font-medium"
      >
        {{ link.label }}
      </router-link>
      <button class="rounded-lg px-3 py-2.5 text-left text-fg/50 hover:bg-fg/5" @click="handleLogout">Выйти</button>
    </nav>
  </header>
</template>
