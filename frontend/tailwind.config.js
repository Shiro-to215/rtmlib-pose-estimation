/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // App Theme tokens mapped 1:1 from CustomTkinter survey
        app: {
          bg: '#F2F5F4',            // BG_WINDOW
          panel: '#FFFFFF',         // BG_PANEL
          subtle: '#EBF0EE',        // BG_SUBTLE
          header: '#F8FAFA',        // BG_HEADER
          row: '#FFFFFF',           // BG_ROW
          'row-hover': '#F4F9F8',   // BG_ROW_HOVER
          'row-selected': '#E2F2EE',// BG_ROW_SELECTED
          border: '#D4DFDC',        // BORDER
          'border-strong': '#B2C4BE',// BORDER_STRONG
          'border-focus': '#0F766E', // BORDER_FOCUS
        },
        primary: {
          DEFAULT: '#0F766E',       // TEAL
          hover: '#115E59',         // TEAL_HOVER
          soft: '#E4F3F0',          // TEAL_SOFT
          'soft-hover': '#D0EBE6',  // TEAL_SOFT_HOVER
          text: '#0B534D',          // TEAL_TEXT
        },
        pose: {
          DEFAULT: '#0369A1',       // POSE_BLUE
          soft: '#E0F2FE',          // POSE_SOFT
        },
        danger: {
          DEFAULT: '#C8332B',       // DANGER
          hover: '#A62620',         // DANGER_HOVER
          soft: '#FEF2F2',          // DANGER_SOFT
          border: '#F5C2C0',        // DANGER_BORDER
        },
        success: {
          DEFAULT: '#15803D',       // SUCCESS
          soft: '#DCFCE7',          // SUCCESS_SOFT
        },
        text: {
          primary: '#1E293B',       // TEXT_PRIMARY (Slate 800)
          secondary: '#475569',     // TEXT_SECONDARY (Slate 600)
          muted: '#64748B',         // TEXT_MUTED (Slate 500)
        },
        log: {
          bg: '#F8FAFC',            // LOG_BG
          border: '#CBD5E1',        // LOG_BORDER
        },
        preview: {
          bg: '#E2E8E6',            // PREVIEW_BG
        }
      },
      fontFamily: {
        sans: [
          'Yu Gothic UI',
          'Meiryo UI',
          'BIZ UDPGothic',
          'Hiragino Sans',
          'Segoe UI',
          'sans-serif'
        ],
        mono: [
          'BIZ UDGothic',
          'Cascadia Mono',
          'Consolas',
          'monospace'
        ]
      }
    },
  },
  plugins: [],
};
