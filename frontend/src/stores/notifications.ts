import { defineStore } from "pinia";
import { ref } from "vue";

import * as notificationsApi from "@/api/notifications";
import type { Notification } from "@/types";

const POLL_INTERVAL_MS = 30_000;

export const useNotificationsStore = defineStore("notifications", () => {
  const items = ref<Notification[]>([]);
  const unreadCount = ref(0);
  let pollTimer: ReturnType<typeof setInterval> | null = null;

  async function fetchUnreadCount() {
    const res = await notificationsApi.getUnreadCount();
    unreadCount.value = res.count;
  }

  async function fetchList() {
    items.value = await notificationsApi.listNotifications();
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
  }

  return {
    items,
    unreadCount,
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
