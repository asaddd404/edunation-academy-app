/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "rgb(var(--ink) / <alpha-value>)",
        "ink-2": "rgb(var(--ink-2) / <alpha-value>)",
        "ink-3": "rgb(var(--ink-3) / <alpha-value>)",
        sand: "rgb(var(--sand) / <alpha-value>)",
        paper: "rgb(var(--paper) / <alpha-value>)",
        "paper-2": "rgb(var(--paper-2) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        "line-strong": "rgb(var(--line-strong) / <alpha-value>)",
        moss: "rgb(var(--moss) / <alpha-value>)",
        "moss-fg": "rgb(var(--moss-fg) / <alpha-value>)",
        marigold: "rgb(var(--marigold) / <alpha-value>)",
        clay: "rgb(var(--clay) / <alpha-value>)",
        "brand-header": "rgb(var(--brand-header) / <alpha-value>)",
        "brand-header-fg": "rgb(var(--brand-header-fg) / <alpha-value>)",
      },
      borderRadius: { DEFAULT: "var(--radius)" },
      fontFamily: {
        display: ["Literata", "ui-serif", "serif"],
        body: ["Inter", "ui-sans-serif", "sans-serif"],
      },
      fontSize: {
        "display-lg": ["2rem", { lineHeight: "2.5rem", fontWeight: "600" }],
        "display-sm": ["1.375rem", { lineHeight: "1.875rem", fontWeight: "600" }],
        "body-lg": ["1.0625rem", { lineHeight: "1.75rem", fontWeight: "400" }],
        body: ["0.9375rem", { lineHeight: "1.5rem", fontWeight: "400" }],
        label: ["0.8125rem", { lineHeight: "1.125rem", fontWeight: "500" }],
        caption: ["0.75rem", { lineHeight: "1rem", fontWeight: "400" }],
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(16px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        // Sideways counterpart of fade-up, for the mobile catalog stepping
        // one level deeper.
        "drill-in": {
          from: { opacity: "0", transform: "translateX(14px)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
      },
      animation: {
        // `both` keeps the element hidden until its (optionally delayed) run starts.
        "fade-up": "fade-up 0.6s cubic-bezier(0.16, 1, 0.3, 1) both",
        "fade-in": "fade-in 0.5s ease-out both",
        "drill-in": "drill-in 0.2s ease-out both",
      },
    },
  },
  plugins: [],
};
