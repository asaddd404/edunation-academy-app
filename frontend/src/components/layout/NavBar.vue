<script setup lang="ts">
import { Bell, GraduationCap, LogOut, Menu, Moon, Sun, X } from "@lucide/vue";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";
import { useNotificationsStore } from "@/stores/notifications";
import { useThemeStore } from "@/stores/theme";

const auth = useAuthStore();
const router = useRouter();
const notifications = useNotificationsStore();
const theme = useThemeStore();

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
const mobileMenuRoot = ref<HTMLElement | null>(null);
const mobileMenuButton = ref<HTMLElement | null>(null);
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
  if (
    mobileMenuOpen.value &&
    mobileMenuRoot.value &&
    !mobileMenuRoot.value.contains(event.target as Node) &&
    mobileMenuButton.value &&
    !mobileMenuButton.value.contains(event.target as Node)
  ) {
    closeMobileMenu();
  }
}

function handleEscapeKey(event: KeyboardEvent) {
  if (event.key === "Escape" && mobileMenuOpen.value) closeMobileMenu();
}

// Body scroll is locked while the drawer covers the screen -- restores
// whatever value was there before (rather than assuming "") so this
// doesn't clobber a lock some other overlay might already hold.
let previousBodyOverflow = "";
watch(mobileMenuOpen, (isOpen) => {
  if (isOpen) {
    previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  } else {
    document.body.style.overflow = previousBodyOverflow;
  }
});

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

onMounted(() => {
  document.addEventListener("click", handleClickOutside);
  document.addEventListener("keydown", handleEscapeKey);
});
onBeforeUnmount(() => {
  document.removeEventListener("click", handleClickOutside);
  document.removeEventListener("keydown", handleEscapeKey);
  // In case the component unmounts while the drawer is open (route change
  // away from an authenticated layout), don't leave scrolling locked.
  document.body.style.overflow = previousBodyOverflow;
});

function handleLogout() {
  auth.logout();
  router.push("/login");
}
</script>

<template>
  <header class="sticky top-0 z-50 w-full border-b border-line bg-paper/90 backdrop-blur-md">
    <div class="flex h-16 w-full items-center justify-between px-4 sm:px-6 lg:px-8">
      <router-link
        to="/"
        class="flex shrink-0 items-center gap-2 font-display text-lg font-semibold tracking-tight text-ink transition-opacity hover:opacity-70"
      >
        <span class="flex h-8 w-8 items-center justify-center rounded-lg bg-moss text-moss-fg">
          <GraduationCap :size="18" :stroke-width="2" />
        </span>
        <span class="hidden sm:inline">Edunation Academy</span>
      </router-link>

      <nav v-if="auth.isAuthenticated" class="hidden flex-1 items-center justify-center gap-1 md:flex">
        <router-link
          v-for="link in links"
          :key="link.to"
          :to="link.to"
          class="relative rounded-lg px-3 py-2 text-body text-ink-2 transition-colors hover:bg-paper-2 hover:text-ink"
          exact-active-class="!text-ink font-medium after:absolute after:inset-x-3 after:-bottom-[1px] after:h-[3px] after:rounded-full after:bg-marigold"
        >
          {{ link.label }}
        </router-link>
      </nav>

      <div class="flex shrink-0 items-center gap-1 sm:gap-2">
        <button
          class="flex h-11 w-11 items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-paper-2 hover:text-ink"
          :aria-label="theme.theme === 'dark' ? 'Включить светлую тему' : 'Включить тёмную тему'"
          @click="theme.toggle"
        >
          <Sun v-if="theme.theme === 'dark'" :size="18" :stroke-width="1.8" />
          <Moon v-else :size="18" :stroke-width="1.8" />
        </button>

        <div v-if="!auth.isAuthenticated" class="flex items-center gap-1.5 sm:gap-2">
          <router-link
            to="/login"
            class="rounded-lg px-2.5 py-1.5 text-body text-ink-2 transition-colors duration-200 hover:bg-paper-2 hover:text-ink sm:px-3"
          >
            Войти
          </router-link>
          <router-link to="/register" class="btn-primary px-3 py-1.5 text-sm sm:px-4"> Регистрация </router-link>
        </div>

        <button
          v-if="auth.isAuthenticated"
          ref="mobileMenuButton"
          class="flex h-11 w-11 items-center justify-center rounded-lg text-ink-3 hover:bg-paper-2 hover:text-ink md:hidden"
          :aria-expanded="mobileMenuOpen"
          aria-controls="mobile-drawer"
          aria-label="Меню"
          @click="mobileMenuOpen = !mobileMenuOpen"
        >
          <Menu v-if="!mobileMenuOpen" :size="20" :stroke-width="1.8" class="pointer-events-none" />
          <X v-else :size="20" :stroke-width="1.8" class="pointer-events-none" />
        </button>

        <div v-if="auth.isAuthenticated" ref="bellRoot" class="relative">
          <button
            class="relative flex h-11 w-11 items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-paper-2 hover:text-ink"
            aria-label="Уведомления"
            @click.stop="toggleDropdown"
          >
            <Bell :size="18" :stroke-width="1.8" />
            <span
              v-if="notifications.unreadCount > 0"
              class="absolute right-1.5 top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-clay px-1 text-[10px] font-medium text-white"
            >
              {{ notifications.unreadCount > 9 ? "9+" : notifications.unreadCount }}
            </span>
          </button>

          <div
            v-if="dropdownOpen"
            class="absolute right-0 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-line bg-paper shadow-lg"
          >
            <div class="flex items-center justify-between border-b border-line px-3 py-2">
              <span class="text-sm font-medium text-ink">Уведомления</span>
              <div class="flex items-center gap-3">
                <button
                  v-if="notifications.items.some((n) => !n.is_read)"
                  class="text-xs text-moss underline underline-offset-2 hover:opacity-70"
                  @click="notifications.markAllRead"
                >
                  Прочитать все
                </button>
                <button
                  v-if="notifications.items.length"
                  class="text-xs text-ink-3 hover:text-clay hover:underline"
                  @click="handleClearAll"
                >
                  Очистить всё
                </button>
              </div>
            </div>
            <ul class="max-h-96 overflow-y-auto">
              <li v-if="notifications.items.length === 0" class="px-3 py-6 text-center text-sm text-ink-3">
                Пока нет уведомлений
              </li>
              <li
                v-for="notification in notifications.items"
                :key="notification.id"
                class="group flex cursor-pointer items-start gap-2 border-b border-line px-3 py-3 text-sm last:border-b-0 hover:bg-paper-2"
                :class="{ 'bg-marigold/10': !notification.is_read }"
                @click="handleNotificationClick(notification)"
              >
                <div class="flex-1">
                  <p :class="notification.is_read ? 'text-ink-3' : 'font-medium text-ink'">
                    {{ notification.message }}
                  </p>
                  <p class="mt-1 text-xs text-ink-3">
                    {{ new Date(notification.created_at).toLocaleString("ru-RU") }}
                  </p>
                </div>
                <button
                  class="shrink-0 rounded p-1 text-ink-3 opacity-0 hover:text-clay group-hover:opacity-100"
                  aria-label="Удалить уведомление"
                  @click="handleDeleteNotification($event, notification.id)"
                >
                  <X :size="14" :stroke-width="1.8" />
                </button>
              </li>
            </ul>
            <div v-if="notifications.hasMore" class="border-t border-line p-2">
              <button
                class="w-full rounded-lg px-3 py-2 text-center text-xs font-medium text-ink-2 hover:bg-paper-2 hover:text-ink disabled:opacity-50"
                :disabled="notifications.loadingMore"
                @click="notifications.loadMore"
              >
                {{ notifications.loadingMore ? "Загрузка…" : "Показать ещё" }}
              </button>
            </div>
          </div>
        </div>

        <router-link
          v-if="auth.isAuthenticated"
          to="/profile"
          class="hidden items-center rounded-lg px-2.5 py-1.5 text-body text-ink-2 transition-colors hover:bg-paper-2 hover:text-ink md:flex"
        >
          {{ auth.user?.first_name }}
        </router-link>

        <button
          v-if="auth.isAuthenticated"
          class="hidden h-11 w-11 items-center justify-center rounded-lg text-ink-3 transition-colors hover:bg-clay/10 hover:text-clay md:flex"
          aria-label="Выйти"
          title="Выйти"
          @click="handleLogout"
        >
          <LogOut :size="18" :stroke-width="1.8" />
        </button>
      </div>
    </div>

    <nav
      v-if="auth.isAuthenticated && mobileMenuOpen"
      id="mobile-drawer"
      ref="mobileMenuRoot"
      class="motion-safe:animate-fade-in flex flex-col gap-1 border-t border-line px-4 py-3 text-sm md:hidden"
      @keydown.esc="closeMobileMenu"
    >
      <router-link
        v-for="link in links"
        :key="link.to"
        :to="link.to"
        class="flex min-h-11 items-center rounded-lg px-3 py-2.5 text-ink-2 hover:bg-paper-2"
        exact-active-class="marker-edge bg-paper-2 font-medium text-ink"
      >
        {{ link.label }}
      </router-link>
      <router-link to="/profile" class="flex min-h-11 items-center rounded-lg px-3 py-2.5 text-ink-2 hover:bg-paper-2">
        Профиль
      </router-link>
      <button
        class="flex min-h-11 items-center gap-2 rounded-lg px-3 py-2.5 text-left text-ink-3 hover:bg-paper-2"
        @click="
          theme.toggle();
          closeMobileMenu();
        "
      >
        <Sun v-if="theme.theme === 'dark'" :size="16" :stroke-width="1.8" />
        <Moon v-else :size="16" :stroke-width="1.8" />
        {{ theme.theme === "dark" ? "Светлая тема" : "Тёмная тема" }}
      </button>
      <button
        class="flex min-h-11 items-center gap-2 rounded-lg px-3 py-2.5 text-left text-ink-3 hover:bg-paper-2"
        @click="handleLogout"
      >
        <LogOut :size="16" :stroke-width="1.8" />
        Выйти
      </button>
    </nav>
  </header>
</template>
