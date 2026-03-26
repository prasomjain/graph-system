/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["Space Grotesk", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        canvas: "#020617",
        panel: "#0f172a",
        panelBorder: "#1e293b",
      },
      boxShadow: {
        panel: "0 8px 40px rgba(2, 6, 23, 0.55)",
      },
    },
  },
  plugins: [],
};
