/**** @type {import('tailwindcss').Config} ****/
module.exports = {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{ts,tsx,js,jsx}'
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          500: '#6366f1',
          600: '#4f46e5'
        }
      }
    }
  },
  plugins: [require('@tailwindcss/typography')]
};
