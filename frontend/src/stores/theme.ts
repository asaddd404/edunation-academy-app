import { defineStore } from "pinia";
import { ref, watch } from "vue";

export type Theme = "light" | "dark";

const THEME_KEY = "edunation_theme";

function detectInitialTheme(): Theme {
  const stored = localStorage.getItem(THEME_KEY);
  if (stored === "light" || stored === "dark") return stored;
  // Light is the site's actual brand look -- a first-time visitor gets it
  // regardless of their OS preference. The toggle in the navbar is still
  // there for anyone who wants dark, and that choice is what gets stored.
  return "light";
}

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

export const useThemeStore = defineStore("theme", () => {
  const theme = ref<Theme>(detectInitialTheme());
  applyTheme(theme.value);

  watch(theme, (value) => {
    localStorage.setItem(THEME_KEY, value);
    applyTheme(value);
  });

  function toggle() {
    theme.value = theme.value === "dark" ? "light" : "dark";
  }

  function setTheme(value: Theme) {
    theme.value = value;
  }

  return { theme, toggle, setTheme };
});
