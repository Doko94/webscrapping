/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#17263a',
        muted: '#6c5b7b',
        panel: '#ffffff',
        soft: '#fbf7f4',
        brand: '#c06c84',
        brandDark: '#8f4b62',
        accent: '#f67280',
        warm: '#f8b195',
        plum: '#6c5b7b',
        ocean: '#355c7d',
      },
      boxShadow: {
        soft: '0 18px 45px rgba(53, 92, 125, 0.11)',
      },
    },
  },
  plugins: [],
}
