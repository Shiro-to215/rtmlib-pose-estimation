/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: '#ECEEEF',
        surface: '#FFFFFF',
        subtle: '#F4F5F6',
        'muted-surface': '#E3E5E8',
        ink: {
          primary: '#111111',
          secondary: '#71717A',
          muted: '#A1A1AA',
        },
        status: {
          active: '#15803D',
          'active-bg': '#DCFCE7',
          danger: '#B91C1C',
          'danger-bg': '#FEE2E2',
        },
      },
      fontFamily: {
        sans: [
          'Inter',
          'Hiragino Sans',
          'Noto Sans JP',
          'BIZ UDPGothic',
          'Yu Gothic UI',
          'Meiryo UI',
          'sans-serif',
        ],
        mono: [
          'JetBrains Mono',
          'Cascadia Mono',
          'SFMono-Regular',
          'Consolas',
          'monospace',
        ],
      },
      borderRadius: {
        card: '14px',
        control: '6px',
        pill: '9999px',
      },
    },
  },
  plugins: [],
};
