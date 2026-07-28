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
      },
    },
  },
  plugins: [],
};
