import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { brand: { 50: "#eef4ff", 100: "#dbe7ff", 500: "#3b6cf6", 600: "#2a55d9", 700: "#2145b3" } },
    },
  },
  plugins: [],
};
export default config;
