import type { Config } from 'tailwindcss';
import animate from 'tailwindcss-animate';

const config: Config = {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      borderRadius: {
        // With --radius: 0.75rem this yields the ladder sm 8 / md 10 / lg 12 (+ stock 2xl 16 and
        // rounded-full for pills), per the Apple-HIG redesign spec §1.3.
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
      // Inter Variable is the app face (self-hosted via @fontsource-variable, imported in main.tsx);
      // the trailing stack covers the pre-font-load flash and any missing glyphs.
      //
      // Diacritic-correct script fonts (group 4.9.2), self-hosted via @fontsource (imported in
      // main.tsx). `font-arabic` / `font-hebrew` apply these to Arabic / Hebrew text regions; Latin
      // glyphs fall back to the default serif/sans (only the script subset of each is bundled).
      fontFamily: {
        sans: [
          '"Inter Variable"',
          '-apple-system',
          'BlinkMacSystemFont',
          '"Segoe UI"',
          'sans-serif',
        ],
        arabic: ['"Noto Naskh Arabic"', 'serif'],
        hebrew: ['"Noto Sans Hebrew"', 'sans-serif'],
      },
      // Apple-style named type scale (spec §2) — ADDITIVE: Tailwind's default text-* sizes are
      // deliberately not redefined (blast-radius control). Weight/tracking ride along in the tuple
      // so e.g. `text-title2` is the complete treatment.
      fontSize: {
        'large-title': [
          '2rem',
          {
            lineHeight: '2.375rem',
            letterSpacing: '-0.02em',
            fontWeight: '700',
          },
        ],
        title1: [
          '1.5rem',
          {
            lineHeight: '1.875rem',
            letterSpacing: '-0.015em',
            fontWeight: '700',
          },
        ],
        title2: [
          '1.25rem',
          {
            lineHeight: '1.5625rem',
            letterSpacing: '-0.01em',
            fontWeight: '600',
          },
        ],
        headline: [
          '1.0625rem',
          {
            lineHeight: '1.375rem',
            letterSpacing: '-0.01em',
            fontWeight: '600',
          },
        ],
        body: [
          '0.9375rem',
          { lineHeight: '1.375rem', letterSpacing: '-0.006em' },
        ],
        subhead: [
          '0.8125rem',
          { lineHeight: '1.125rem', letterSpacing: '-0.003em' },
        ],
        footnote: ['0.75rem', { lineHeight: '1rem' }],
        caption: [
          '0.6875rem',
          {
            lineHeight: '0.8125rem',
            letterSpacing: '0.06em',
            fontWeight: '600',
          },
        ],
      },
      // Explicit alpha-capable mapping so opacity modifiers (`bg-primary/15`, `ring-primary/25`)
      // are guaranteed to resolve against the HSL CSS variables.
      colors: {
        background: 'hsl(var(--background) / <alpha-value>)',
        foreground: 'hsl(var(--foreground) / <alpha-value>)',
        card: {
          DEFAULT: 'hsl(var(--card) / <alpha-value>)',
          foreground: 'hsl(var(--card-foreground) / <alpha-value>)',
        },
        popover: {
          DEFAULT: 'hsl(var(--popover) / <alpha-value>)',
          foreground: 'hsl(var(--popover-foreground) / <alpha-value>)',
        },
        primary: {
          DEFAULT: 'hsl(var(--primary) / <alpha-value>)',
          foreground: 'hsl(var(--primary-foreground) / <alpha-value>)',
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary) / <alpha-value>)',
          foreground: 'hsl(var(--secondary-foreground) / <alpha-value>)',
        },
        muted: {
          DEFAULT: 'hsl(var(--muted) / <alpha-value>)',
          foreground: 'hsl(var(--muted-foreground) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'hsl(var(--accent) / <alpha-value>)',
          foreground: 'hsl(var(--accent-foreground) / <alpha-value>)',
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive) / <alpha-value>)',
          foreground: 'hsl(var(--destructive-foreground) / <alpha-value>)',
        },
        border: 'hsl(var(--border) / <alpha-value>)',
        input: 'hsl(var(--input) / <alpha-value>)',
        ring: 'hsl(var(--ring) / <alpha-value>)',
        // HIG semantic hues (ratings, CEFR, status). In dark mode the `-deep` variables re-point at
        // the vivid hues (index.css), so one tint class string is valid in both modes.
        hig: {
          red: {
            DEFAULT: 'hsl(var(--hig-red) / <alpha-value>)',
            deep: 'hsl(var(--hig-red-deep) / <alpha-value>)',
          },
          orange: {
            DEFAULT: 'hsl(var(--hig-orange) / <alpha-value>)',
            deep: 'hsl(var(--hig-orange-deep) / <alpha-value>)',
          },
          blue: {
            DEFAULT: 'hsl(var(--hig-blue) / <alpha-value>)',
            deep: 'hsl(var(--hig-blue-deep) / <alpha-value>)',
          },
          green: {
            DEFAULT: 'hsl(var(--hig-green) / <alpha-value>)',
            deep: 'hsl(var(--hig-green-deep) / <alpha-value>)',
          },
          gray: 'hsl(var(--hig-gray) / <alpha-value>)',
        },
      },
      // 3-step elevation ladder (values live in index.css so dark mode swaps them wholesale).
      boxShadow: {
        card: 'var(--shadow-card)',
        raised: 'var(--shadow-raised)',
        overlay: 'var(--shadow-overlay)',
      },
      // Apple spring-ish curve for micro-interactions: `ease-apple`.
      transitionTimingFunction: {
        apple: 'var(--ease-apple)',
      },
      // Named 250ms step (dialog/toast enters). tailwindcss-animate mirrors transitionDuration for
      // animation-duration, so `duration-250` drives both — an arbitrary `duration-[250ms]` would
      // be ambiguous between the two plugins and warn at build time.
      transitionDuration: {
        '250': '250ms',
      },
      // Skeleton shimmer (ui/skeleton.tsx): a gradient sweep across the muted block.
      keyframes: {
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.6s linear infinite',
      },
    },
  },
  // Revives the dialog/toast `animate-in`/`animate-out` classes (they were written for this plugin
  // all along) and powers popover/sheet transitions.
  plugins: [animate],
};

export default config;
