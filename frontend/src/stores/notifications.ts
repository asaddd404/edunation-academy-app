import { defineStore } from "pinia";
import { computed, ref } from "vue";

import * as notificationsApi from "@/api/notifications";
import type { Notification } from "@/types";

const POLL_INTERVAL_MS = 30_000;
const PAGE_SIZE = 20;

export const useNotificationsStore = defineStore("notifications", () => {
  const items = ref<Notification[]>([]);
  const unreadCount = ref(0);
  const page = ref(1);
  const totalPages = ref(1);
  const loadingMore = ref(false);
  let pollTimer: ReturnType<typeof setInterval> | null = null;

  const hasMore = computed(() => page.value < totalPages.value);

  async function fetchUnreadCount() {
    const res = await notificationsApi.getUnreadCount();
    unreadCount.value = res.count;
  }

  async function fetchList() {
    const res = await notificationsApi.listNotifications({ page: 1, per_page: PAGE_SIZE });
    items.value = res.items;
    page.value = res.page;
    totalPages.value = res.pages;
  }

  async function loadMore() {
    if (!hasMore.value || loadingMore.value) return;
    loadingMore.value = true;
    try {
      const res = await notificationsApi.listNotifications({ page: page.value + 1, per_page: PAGE_SIZE });
      items.value = [...items.value, ...res.items];
      page.value = res.page;
      totalPages.value = res.pages;
    } finally {
      loadingMore.value = false;
    }
  }

  async function markRead(id: number) {
    const notification = items.value.find((n) => n.id === id);
    if (notification?.is_read) return;
    await notificationsApi.markNotificationRead(id);
    if (notification) notification.is_read = true;
    await fetchUnreadCount();
  }

  async function markAllRead() {
    await notificationsApi.markAllNotificationsRead();
    items.value.forEach((n) => (n.is_read = true));
    unreadCount.value = 0;
  }

  async function remove(id: number) {
    const notification = items.value.find((n) => n.id === id);
    await notificationsApi.deleteNotification(id);
    items.value = items.value.filter((n) => n.id !== id);
    if (notification && !notification.is_read) {
      unreadCount.value = Math.max(0, unreadCount.value - 1);
    }
  }

  async function clearAll() {
    await notificationsApi.clearAllNotifications();
    items.value = [];
    unreadCount.value = 0;
    page.value = 1;
    totalPages.value = 1;
  }

  function startPolling() {
    if (pollTimer) return;
    fetchUnreadCount();
    pollTimer = setInterval(fetchUnreadCount, POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
    items.value = [];
    unreadCount.value = 0;
    page.value = 1;
    totalPages.value = 1;
  }

  return {
    items,
    unreadCount,
    hasMore,
    loadingMore,
    loadMore,
    fetchUnreadCount,
    fetchList,
    markRead,
    markAllRead,
    remove,
    clearAll,
    startPolling,
    stopPolling,
  };
});
