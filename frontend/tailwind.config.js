/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        brand: {
          50: "#f2f6ff",
          100: "#e3ebff",
          200: "#c3d3ff",
          300: "#9bb2ff",
          400: "#7089ff",
          500: "#4d63f7",
          600: "#3a47db",
          700: "#2f38b0",
          800: "#28308c",
          900: "#242c6f",
        },
        accent: {
          400: "#22d3c8",
          500: "#0fb8ac",
          600: "#0a9a90",
        },
        ink: {
          900: "#0b0e1a",
          800: "#11152a",
          700: "#171c36",
        },
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(77,99,247,0.08), 0 8px 24px -4px rgba(77,99,247,0.25)",
        card: "0 1px 2px rgba(15,23,42,0.04), 0 8px 24px -8px rgba(15,23,42,0.08)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: 0, transform: "translateY(6px)" },
          "100%": { opacity: 1, transform: "translateY(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.25s ease-out",
        shimmer: "shimmer 2.2s linear infinite",
      },
    },
  },
  plugins: [],
};
