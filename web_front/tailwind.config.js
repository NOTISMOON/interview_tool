/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#E0F7F4',
          100: '#B2EBE0',
          200: '#80DBCA',
          300: '#4DC9B4',
          400: '#26BFA5',
          500: '#00BFA5',
          600: '#00A88A',
          700: '#008F73',
          800: '#00755E',
          900: '#005C49',
        },
        ink: {
          50: '#F7F8FA',
          100: '#EFF1F4',
          200: '#D8DBE0',
          300: '#B3B8C0',
          400: '#8A8F99',
          500: '#666666',
          600: '#4A4D53',
          700: '#3A3D42',
          800: '#2A2C30',
          900: '#232529',
        },
      },
    },
  },
  plugins: [],
  corePlugins: {
    preflight: false,
  },
};