import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { brand: { 50: "#eef2ff", 100: "#e0e7ff", 300: "#a5b4fc", 500: "#6366f1", 600: "#4f46e5", 700: "#3730a3" } },
    },
  },
  plugins: [],
};
export default config;
