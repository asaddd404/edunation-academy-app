import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL as string,
  // The refresh token is an httpOnly cookie now. Same-origin requests would
  // carry it regardless, and in production the API is same-origin -- but this
  // is what keeps the session working if VITE_API_BASE_URL is ever pointed at
  // another host, rather than failing in a way that looks like a server bug.
  withCredentials: true,
});

interface RetriableConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
  _busyRetries?: number;
}

/**
 * A busy server answers 503 (or 429) with Retry-After. Retrying after it
 * turns a moment of overload into a short pause instead of an error toast.
 *
 * Reads are always safe to repeat. A write is repeated only when the
 * response carries X-Load-Shed -- turned away before its handler ran. A 503
 * without it can come from a handler that already committed and then could
 * not get a connection back (an ЕНТ submit), and resending that would turn
 * success into "already submitted". Short waits only: a longer Retry-After
 * is a real limit, not a blip.
 */
const MAX_BUSY_RETRIES = 2;
const MAX_BUSY_WAIT_MS = 3000;

function busyRetryDelay(error: AxiosError, config: RetriableConfig): number | null {
  const status = error.response?.status;
  const isRead = (config.method ?? "get").toLowerCase() === "get";
  const neverRan = error.response?.headers?.["x-load-shed"] === "1";
  if ((status !== 503 && status !== 429) || !(isRead || neverRan)) return null;
  if ((config._busyRetries ?? 0) >= MAX_BUSY_RETRIES) return null;
  const retryAfter = Number(error.response?.headers?.["retry-after"]) * 1000;
  if (!Number.isFinite(retryAfter)) return 1000;
  if (retryAfter > MAX_BUSY_WAIT_MS) return null;
  // Jitter, so a classroom shed at once does not come back at once.
  return Math.max(retryAfter, 500) * (0.75 + Math.random() * 0.5);
}

let refreshPromise: Promise<string | null> | null = null;

http.interceptors.request.use(async (config) => {
  // Dynamic import to avoid a circular dependency between the store and this module.
  const { useAuthStore } = await import("@/stores/auth");
  const auth = useAuthStore();
  if (auth.accessToken) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`;
  }
  return config;
});

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetriableConfig | undefined;
    const busyDelay = originalRequest ? busyRetryDelay(error, originalRequest) : null;
    if (originalRequest && busyDelay !== null) {
      originalRequest._busyRetries = (originalRequest._busyRetries ?? 0) + 1;
      await new Promise((resolve) => setTimeout(resolve, busyDelay));
      return http(originalRequest);
    }
    if (error.response?.status !== 401 || !originalRequest || originalRequest._retry) {
      return Promise.reject(error);
    }
    if (originalRequest.url?.includes("/auth/refresh") || originalRequest.url?.includes("/auth/login")) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    const { useAuthStore } = await import("@/stores/auth");
    const auth = useAuthStore();

    if (!refreshPromise) {
      refreshPromise = auth.refresh().finally(() => {
        refreshPromise = null;
      });
    }

    const newAccessToken = await refreshPromise;
    if (!newAccessToken) {
      // No `logout()` call here: a failed refresh has already cleared the
      // store, and the server cleared the cookie on its way to the 401.
      // Posting to /auth/logout as well would only be a second request that
      // cannot change anything.
      return Promise.reject(error);
    }

    originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
    return http(originalRequest);
  },
);

export default http;
