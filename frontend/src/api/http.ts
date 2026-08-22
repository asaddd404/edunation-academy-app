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
