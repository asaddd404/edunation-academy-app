import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL as string,
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
      auth.logout();
      return Promise.reject(error);
    }

    originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
    return http(originalRequest);
  },
);

export default http;
