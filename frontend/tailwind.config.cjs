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
        // Neo-Brutalist Tech-Forward Palette
        brand: {
          50: '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          800: '#1e293b',
          900: '#0f172a',
        },
        // Neo-Brutalist core colors
        brutal: {
          black: '#000000',
          white: '#FFFFFF',
          blue: '#0066FF',
          green: '#A8E6A3',  // Softer pastel green - easier on eyes
          yellow: '#FFE666',  // Softer pastel yellow - easier on eyes
          red: '#FF0000',
          gray: '#333333',
          'code-bg': '#f5f5f5',  // Light gray background for better readability
          'code-text': '#1a1a1a', // Dark text on light background
        },
        // Legacy colors for gradual migration
        accent: {
          50: '#fafaf9',
          100: '#f5f5f4',
          200: '#e7e5e4',
          300: '#d6d3d1',
          400: '#a8a29e',
          500: '#78716c',
          600: '#57534e',
          700: '#44403c',
        },
        primary: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
        }
      },
      boxShadow: {
        'brutal-sm': '2px 2px 0px #000000',
        'brutal': '4px 4px 0px #000000',
        'brutal-lg': '6px 6px 0px #000000',
        'brutal-xl': '8px 8px 0px #000000',
        'brutal-blue': '4px 4px 0px #0066FF',
        'brutal-green': '4px 4px 0px #00FF00',
      },
      borderWidth: {
        '3': '3px',
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
          '50%': { opacity: '0.6' }
        },
        // Neo-brutalist animations - quick, harsh, mechanical
        brutalPop: {
          '0%': { transform: 'scale(0.95)' },
          '100%': { transform: 'scale(1)' }
        },
        brutalBlink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' }
        },
        brutalSlide: {
          '0%': { transform: 'translateX(-4px)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' }
        },
        brutalDrop: {
          '0%': { transform: 'translateY(-8px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' }
        },
        viewFade: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' }
        },
        brutalGlitch: {
          '0%, 100%': { transform: 'translate(0, 0)' },
          '33%': { transform: 'translate(-2px, 0)' },
          '66%': { transform: 'translate(2px, 0)' }
        },
        brutalShake: {
          '0%, 100%': { transform: 'translateX(0)' },
          '25%': { transform: 'translateX(-2px)' },
          '75%': { transform: 'translateX(2px)' }
        },
        brutalSpinOuter: {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' }
        },
        brutalSpinInner: {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(-360deg)' }
        },
        brutalProgressSegment: {
          '0%, 100%': {
            backgroundColor: '#FFFFFF',
            borderColor: '#000000'
          },
          '25%': {
            backgroundColor: '#0066FF',
            borderColor: '#FFFFFF'
          },
          '50%': {
            backgroundColor: '#FFE666',
            borderColor: '#000000'
          },
          '75%': {
            backgroundColor: '#A8E6A3',
            borderColor: '#FFFFFF'
          }
        },
        brutalBounce: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-4px)' }
        },
        brutalSlideBar: {
          '0%': { left: '-33%' },
          '100%': { left: '100%' }
        }
      },
      animation: {
        shimmer: 'shimmer 3s linear infinite',
        slideIn: 'slideIn 0.3s ease-out',
        fadeIn: 'fadeIn 0.4s ease-out',
        scaleIn: 'scaleIn 0.3s ease-out',
        pulse: 'pulse 2s ease-in-out infinite',
        'brutal-pop': 'brutalPop 0.15s linear',
        'brutal-blink': 'brutalBlink 1s step-end infinite',
        'brutal-slide': 'brutalSlide 0.2s linear',
        'brutal-drop': 'brutalDrop 0.15s linear',
        'brutal-glitch': 'brutalGlitch 0.3s linear infinite',
        'brutal-shake': 'brutalShake 0.2s linear',
        'brutal-spin-outer': 'brutalSpinOuter 3s linear infinite',
        'brutal-spin-inner': 'brutalSpinInner 2s linear infinite',
        'brutal-progress': 'brutalProgressSegment 2s linear infinite',
        'view-fade': 'viewFade 0.3s ease-out'
      },
      fontFamily: {
        'mono': [
          'Consolas',
          'JetBrains Mono',
          'Fira Code',
          'SFMono-Regular',
          'Menlo',
          'Monaco',
          'Liberation Mono',
          'Ubuntu Mono',
          'DejaVu Sans Mono',
          'Segoe UI Symbol',
          'Courier New',
          'monospace'
        ],
        'brutal': ['Arial Black', 'Arial', 'sans-serif'],
      }
    }
  },
  plugins: [require('@tailwindcss/typography')]
};
