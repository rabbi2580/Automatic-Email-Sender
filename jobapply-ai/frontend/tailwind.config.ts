import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { brand: { 50: "#eaf5f0", 100: "#d1e9df", 500: "#18836c", 600: "#126c59", 700: "#0e5547" } },
    },
  },
  plugins: [],
};
export default config;
