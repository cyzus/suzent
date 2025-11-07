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
          400: '#818cf8',
          500: '#6366f1',
          600: '#4f46e5'
        }
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '200% 0' },
          '100%': { backgroundPosition: '-200% 0' }
        },
        slideIn: {
          '0%': { opacity: '0', transform: 'translateY(-8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' }
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' }
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' }
        },
        pulse: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.7' }
        }
      },
      animation: {
        shimmer: 'shimmer 2.5s linear infinite',
        slideIn: 'slideIn 0.3s ease-out',
        fadeIn: 'fadeIn 0.4s ease-out',
        scaleIn: 'scaleIn 0.3s ease-out',
        pulse: 'pulse 2s ease-in-out infinite'
      }
    }
  },
  plugins: [require('@tailwindcss/typography')]
};
