/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: 'rgb(var(--color-primary) / 0.05)',
          100: 'rgb(var(--color-primary) / 0.1)',
          200: 'rgb(var(--color-primary) / 0.2)',
          300: 'rgb(var(--color-primary) / 0.4)',
          400: 'rgb(var(--color-primary) / 0.7)',
          500: 'rgb(var(--color-primary) / <alpha-value>)',
          600: 'rgb(var(--color-primary-dark) / <alpha-value>)',
          700: 'rgb(var(--color-primary-dark) / 0.9)',
          800: 'rgb(var(--color-primary-dark) / 0.8)',
          900: 'rgb(var(--color-primary-dark) / 0.7)',
          950: 'rgb(var(--color-primary-dark) / 0.6)',
        },
        secondary: {
          50: 'rgb(var(--color-secondary) / 0.05)',
          100: 'rgb(var(--color-secondary) / 0.1)',
          200: 'rgb(var(--color-secondary) / 0.2)',
          300: 'rgb(var(--color-secondary) / 0.4)',
          400: 'rgb(var(--color-secondary) / 0.7)',
          500: 'rgb(var(--color-secondary) / <alpha-value>)',
          600: 'rgb(var(--color-secondary) / 0.9)',
          700: 'rgb(var(--color-secondary) / 0.8)',
          800: 'rgb(var(--color-secondary) / 0.7)',
          900: 'rgb(var(--color-secondary) / 0.6)',
          950: 'rgb(var(--color-secondary) / 0.5)',
        },
        accent: {
          50: 'rgb(var(--color-accent) / 0.05)',
          100: 'rgb(var(--color-accent) / 0.1)',
          200: 'rgb(var(--color-accent) / 0.2)',
          300: 'rgb(var(--color-accent) / 0.4)',
          400: 'rgb(var(--color-accent) / 0.7)',
          500: 'rgb(var(--color-accent) / <alpha-value>)',
          600: 'rgb(var(--color-accent) / 0.9)',
          700: 'rgb(var(--color-accent) / 0.8)',
          800: 'rgb(var(--color-accent) / 0.7)',
          900: 'rgb(var(--color-accent) / 0.6)',
          950: 'rgb(var(--color-accent) / 0.5)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
      boxShadow: {
        'soft': '0 2px 15px -3px rgba(0, 0, 0, 0.07), 0 10px 20px -2px rgba(0, 0, 0, 0.04)',
        'card': '0 0 0 1px rgba(0, 0, 0, 0.05), 0 1px 3px rgba(0, 0, 0, 0.1)',
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-in-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-down': 'slideDown 0.3s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideDown: {
          '0%': { transform: 'translateY(-10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
};
