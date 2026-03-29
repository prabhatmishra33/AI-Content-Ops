import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef9f7",
          100: "#d6f2ec",
          500: "#0c8a7a",
          700: "#0a5f56"
        }
      }
    }
  },
  plugins: []
};

export default config;
