/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./flaskr/templates/**/*.html",
    "./flaskr/static/src/input.css",
  ],
  theme: {
    extend: {},
  },
  plugins: [require("daisyui")],
}
