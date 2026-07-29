/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        accent: "hsl(var(--color-accent) / <alpha-value>)",
        bg: "hsl(var(--color-bg) / <alpha-value>)",
        fg: "hsl(var(--color-fg) / <alpha-value>)",
        card: "hsl(var(--color-card) / <alpha-value>)",
        border: "hsl(var(--color-border) / <alpha-value>)",
        pop: "hsl(var(--color-pop) / <alpha-value>)",
      },
      boxShadow: {
        glow: "0 0 0 1px hsl(var(--color-pop) / 0.4), 0 0 24px 0 hsl(var(--color-pop) / 0.45)",
      },
    },
  },
  plugins: [],
};
