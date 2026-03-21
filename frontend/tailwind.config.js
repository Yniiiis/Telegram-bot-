/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        spotify: {
          base: "#121212",
          elevated: "#181818",
          highlight: "#282828",
          border: "#2a2a2a",
          muted: "#a7a7a7",
          accent: "#1ed760",
          accentHover: "#1fdf64",
        },
      },
      fontFamily: {
        sans: [
          "ui-rounded",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      spacing: {
        nav: "4.5rem",
        player: "5.25rem",
      },
    },
  },
  plugins: [],
};
