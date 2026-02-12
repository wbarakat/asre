import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-geist-sans)"],
        mono: ["var(--font-geist-mono)"],
        serif: ["var(--font-serif)", "Georgia", "serif"],
      },
      colors: {
        dark: {
          DEFAULT: "#000000",
          100: "#0A0A0A",
          200: "#111111",
          300: "#1A1A1A",
          400: "#222222",
          500: "#2A2A2A",
          600: "#333333",
          700: "#444444",
        },
        text: {
          DEFAULT: "rgba(255,255,255,1)",
          75: "rgba(255,255,255,0.75)",
          60: "rgba(255,255,255,0.60)",
          40: "rgba(255,255,255,0.40)",
          25: "rgba(255,255,255,0.25)",
          20: "rgba(255,255,255,0.20)",
        },
        accent: {
          DEFAULT: "#60A5FA",
          light: "#93C5FD",
          dark: "#3B82F6",
        },
        status: {
          yes: "#34D399",
          partial: "#FBBF24",
          no: "rgba(255,255,255,0.20)",
        },
      },
    },
  },
  plugins: [],
};

export default config;
