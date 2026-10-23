import { createPinia } from "pinia";
import { createApp } from "vue";

import App from "@/App.vue";
import router from "@/router";
import { useToastStore } from "@/stores/toast";
import { describeApiError, isHandledElsewhere } from "@/utils/apiError";

import "@/assets/main.css";

const app = createApp(App);
const pinia = createPinia();

app.use(pinia);
app.use(router);

// The safety net under every handler that forgot a `catch`. Before it, a
// failed click -- approving an application, opening notifications -- did
// nothing visible at all: the error only reached the console. Places that
// handle their own errors (inline messages, retry buttons) never get here.
const toasts = useToastStore(pinia);

function reportUnhandled(error: unknown) {
  if (isHandledElsewhere(error)) return;
  console.error(error);
  toasts.push(describeApiError(error));
}

app.config.errorHandler = (error) => reportUnhandled(error);
window.addEventListener("unhandledrejection", (event) => {
  event.preventDefault();
  reportUnhandled(event.reason);
});

app.mount("#app");
