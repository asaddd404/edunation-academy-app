<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";
import { useNotificationsStore } from "@/stores/notifications";

const auth = useAuthStore();
const router = useRouter();
const notifications = useNotificationsStore();

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
      { to: "/teacher", label: "Заявки" },
      { to: "/teacher/categories", label: "Мои категории" },
      { to: "/teacher/homework", label: "Домашки" },
      { to: "/teacher/ent", label: "Банк ЕНТ" },
    ];
  }
  return [];
});

const bellRoot = ref<HTMLElement | null>(null);
const dropdownOpen = ref(false);

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

watch(
  () => auth.isAuthenticated,
  (isAuthenticated) => {
    if (isAuthenticated) notifications.startPolling();
    else notifications.stopPolling();
  },
  { immediate: true },
);

onMounted(() => document.addEventListener("click", handleClickOutside));
onBeforeUnmount(() => document.removeEventListener("click", handleClickOutside));

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

        <div ref="bellRoot" class="relative">
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
            class="absolute right-0 mt-2 w-80 rounded-xl border border-fg/10 bg-bg shadow-lg"
          >
            <div class="flex items-center justify-between border-b border-fg/10 px-3 py-2">
              <span class="text-sm font-medium">Уведомления</span>
              <button
                v-if="notifications.items.some((n) => !n.is_read)"
                class="text-xs text-accent hover:underline"
                @click="notifications.markAllRead"
              >
                Прочитать все
              </button>
            </div>
            <ul class="max-h-96 overflow-y-auto">
              <li v-if="notifications.items.length === 0" class="px-3 py-6 text-center text-sm text-fg/50">
                Пока нет уведомлений
              </li>
              <li
                v-for="notification in notifications.items"
                :key="notification.id"
                class="cursor-pointer border-b border-fg/5 px-3 py-3 text-sm last:border-b-0 hover:bg-fg/5"
                :class="{ 'bg-accent/5': !notification.is_read }"
                @click="handleNotificationClick(notification)"
              >
                <p :class="notification.is_read ? 'text-fg/60' : 'font-medium text-fg'">{{ notification.message }}</p>
                <p class="mt-1 text-xs text-fg/40">{{ new Date(notification.created_at).toLocaleString("ru-RU") }}</p>
              </li>
            </ul>
          </div>
        </div>

        <button class="text-fg/50 hover:text-fg" @click="handleLogout">Выйти</button>
      </nav>
    </div>
  </header>
</template>
