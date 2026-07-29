/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        forex: {
          bg: '#0a0e17',
          surface: '#111827',
          'surface-light': '#1a2332',
          panel: 'rgba(255,255,255,0.03)',
          border: 'rgba(255,255,255,0.06)',
          'border-light': 'rgba(255,255,255,0.1)',
          bullish: '#00d4aa',
          'bullish-dim': 'rgba(0,212,170,0.15)',
          bearish: '#ff4d6a',
          'bearish-dim': 'rgba(255,77,106,0.15)',
          cyan: '#06b6d4',
          text: '#e2e8f0',
          'text-dim': '#94a3b8',
          'text-muted': '#64748b',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      backdropBlur: {
        xs: '2px',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
};
