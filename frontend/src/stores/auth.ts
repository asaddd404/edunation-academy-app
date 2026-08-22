import { defineStore } from "pinia";
import { computed, ref } from "vue";

import * as authApi from "@/api/auth";
import type { Role, User } from "@/types";

/**
 * Where the refresh token used to live.
 *
 * It is now an httpOnly cookie, so this key is only read once per browser --
 * to hand a pre-existing session back to the server, which returns it as a
 * cookie. Without that one-shot migration the switch would sign out every
 * pupil and teacher the next time they opened the app, which for most of
 * them is the middle of a lesson.
 *
 * Delete this constant, and `migrateLegacySession` below, one release after
 * this ships -- by then every active session has been converted, and what
 * remains under the key is an expired token nobody can use.
 */
const LEGACY_REFRESH_TOKEN_KEY = "edunation_refresh_token";

export const useAuthStore = defineStore("auth", () => {
  const user = ref<User | null>(null);
  // Deliberately the only credential this store holds, and only in memory:
  // it expires in fifteen minutes and never touches localStorage, so a
  // closed tab takes it with it.
  const accessToken = ref<string | null>(null);
  const initialized = ref(false);

  const isAuthenticated = computed(() => !!accessToken.value && !!user.value);
  const role = computed<Role | null>(() => user.value?.role ?? null);

  async function register(payload: {
    phone: string;
    password: string;
    first_name: string;
    last_name: string;
  }) {
    const res = await authApi.register(payload);
    accessToken.value = res.access_token;
    user.value = res.user;
  }

  async function login(payload: { phone: string; password: string }) {
    const res = await authApi.login(payload);
    accessToken.value = res.access_token;
    user.value = await authApi.fetchMe();
  }

  async function changePassword(payload: { old_password: string; new_password: string }) {
    // The server revoked every session, so adopt the replacement it just
    // issued -- otherwise the next request would sign this tab out.
    const res = await authApi.changePassword(payload);
    accessToken.value = res.access_token;
  }

  async function refresh(): Promise<string | null> {
    try {
      const res = await authApi.refreshTokens();
      accessToken.value = res.access_token;
      return res.access_token;
    } catch {
      clearSession();
      return null;
    }
  }

  function setUser(updated: User) {
    user.value = updated;
  }

  /** Local state only -- does not tell the server anything. */
  function clearSession() {
    accessToken.value = null;
    user.value = null;
  }

  function logout() {
    clearSession();
    // The cookie is what actually ends the session, and only the server can
    // clear it; failure here is not worth surfacing to someone who is
    // already on their way out.
    authApi.logout().catch(() => undefined);
  }

  /**
   * Converts a pre-cookie session, if this browser has one. Returns the new
   * access token, or null when there was nothing to migrate.
   */
  async function migrateLegacySession(): Promise<string | null> {
    const legacy = localStorage.getItem(LEGACY_REFRESH_TOKEN_KEY);
    if (!legacy) return null;
    // Removed first, and whatever happens next: the token is single-use on
    // the server, so a retry could not succeed anyway, and leaving it behind
    // would keep it readable by script for no benefit.
    localStorage.removeItem(LEGACY_REFRESH_TOKEN_KEY);
    try {
      const res = await authApi.refreshTokens(legacy);
      accessToken.value = res.access_token;
      return res.access_token;
    } catch {
      return null;
    }
  }

  async function initialize() {
    if (initialized.value) return;
    initialized.value = true;

    // Unlike before, there is nothing to check first: the cookie is invisible
    // to this code, so the only way to find out whether a session exists is
    // to ask. An anonymous visitor pays one 401 on first load.
    const token = (await migrateLegacySession()) ?? (await refresh());
    if (token) {
      user.value = await authApi.fetchMe();
    }
  }

  return {
    user,
    accessToken,
    isAuthenticated,
    role,
    register,
    login,
    logout,
    refresh,
    initialize,
    setUser,
    changePassword,
  };
});
