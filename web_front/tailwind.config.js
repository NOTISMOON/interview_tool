/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        flame: {
          50: '#FFF3ED',
          100: '#FFE4D6',
          200: '#FFC9AD',
          300: '#FFA87A',
          400: '#FF8A52',
          500: '#FF6B35',
          600: '#E85D26',
          700: '#C44D1E',
          800: '#9E3D17',
          900: '#7A2E11',
        },
        ink: {
          50: '#F6F8FA',
          100: '#E1E4E8',
          200: '#C4C9D1',
          300: '#8B949E',
          400: '#5F6B7A',
          500: '#3D4552',
          600: '#2C3340',
          700: '#1F2530',
          800: '#141A23',
          900: '#0D1117',
        },
      },
    },
  },
  plugins: [],
  corePlugins: {
    preflight: false,
  },
};