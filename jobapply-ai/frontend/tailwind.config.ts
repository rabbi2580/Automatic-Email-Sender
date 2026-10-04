import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { brand: { 50: "#f0eeff", 100: "#e2dfff", 300: "#b8b0ff", 500: "#897cff", 600: "#6d5dfc", 700: "#5145d8" } },
    },
  },
  plugins: [],
};
export default config;
