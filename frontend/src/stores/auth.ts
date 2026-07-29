import { defineStore } from "pinia";
import { computed, ref } from "vue";

import * as authApi from "@/api/auth";
import type { Role, User } from "@/types";

const REFRESH_TOKEN_KEY = "edunation_refresh_token";

export const useAuthStore = defineStore("auth", () => {
  const user = ref<User | null>(null);
  const accessToken = ref<string | null>(null);
  const refreshToken = ref<string | null>(localStorage.getItem(REFRESH_TOKEN_KEY));
  const initialized = ref(false);

  const isAuthenticated = computed(() => !!accessToken.value && !!user.value);
  const role = computed<Role | null>(() => user.value?.role ?? null);

  function setRefreshToken(token: string | null) {
    refreshToken.value = token;
    if (token) {
      localStorage.setItem(REFRESH_TOKEN_KEY, token);
    } else {
      localStorage.removeItem(REFRESH_TOKEN_KEY);
    }
  }

  async function register(payload: {
    phone: string;
    password: string;
    first_name: string;
    last_name: string;
  }) {
    const res = await authApi.register(payload);
    accessToken.value = res.access_token;
    setRefreshToken(res.refresh_token);
    user.value = res.user;
  }

  async function login(payload: { phone: string; password: string }) {
    const res = await authApi.login(payload);
    accessToken.value = res.access_token;
    setRefreshToken(res.refresh_token);
    user.value = await authApi.fetchMe();
  }

  async function refresh(): Promise<string | null> {
    if (!refreshToken.value) return null;
    try {
      const res = await authApi.refreshTokens(refreshToken.value);
      accessToken.value = res.access_token;
      setRefreshToken(res.refresh_token);
      return res.access_token;
    } catch {
      logout();
      return null;
    }
  }

  function setUser(updated: User) {
    user.value = updated;
  }

  function logout() {
    const token = refreshToken.value;
    accessToken.value = null;
    user.value = null;
    setRefreshToken(null);
    if (token) {
      authApi.logout(token).catch(() => undefined);
    }
  }

  async function initialize() {
    if (initialized.value) return;
    initialized.value = true;
    if (!refreshToken.value) return;
    const token = await refresh();
    if (token) {
      user.value = await authApi.fetchMe();
    }
  }

  return {
    user,
    accessToken,
    refreshToken,
    isAuthenticated,
    role,
    register,
    login,
    logout,
    refresh,
    initialize,
    setUser,
  };
});
