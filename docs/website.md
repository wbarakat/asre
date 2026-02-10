# ASRE Website

The ASRE landing page lives in `website/` and is built with **Next.js 15**, **Tailwind CSS 3**, and **Geist fonts**. It produces a fully static export suitable for any static hosting provider.

## Quick Start

```bash
cd website
npm install
npm run dev       # http://localhost:3000
npm run build     # Static export → website/out/
npm run lint      # ESLint
```

## Architecture

```
website/
  app/
    layout.tsx          # Root layout (Geist fonts, background variant)
    page.tsx            # Page assembly (Navbar → Hero → PainPoints → KeyMetrics → BookCall → Footer)
    globals.css         # Tailwind base + 3 background variants + glass-morphism + animations
  components/
    ui/
      Button.tsx        # Primary/secondary button with sm/md/lg sizes
      Card.tsx          # Glass-morphism wrapper
      AnimatedCounter.tsx  # Scroll-triggered animated number counter
    sections/
      Navbar.tsx        # Fixed nav, blur-on-scroll, mobile menu
      Hero.tsx          # Full-viewport hero with animated entrance
      PainPoints.tsx    # 4-card grid of healthcare data challenges
      KeyMetrics.tsx    # Market + product stats with animated counters
      BookCall.tsx      # Calendly inline embed
      Footer.tsx        # Simple footer with links
  lib/
    constants.ts        # ALL copy, stats, URLs (single source of truth)
    variants.ts         # Background variant switch
    cn.ts               # clsx + tailwind-merge utility
  next.config.ts        # Static export config
  tailwind.config.ts    # Custom colors (primary, dark)
```

## Background Variants

Three dark-mode background variants are defined in `globals.css`:

| Variant | Class | Style |
|---------|-------|-------|
| `mesh` | `.bg-variant-mesh` | Grid lines + radial teal glows (Palantir/Snowflake style) |
| `healthcare` | `.bg-variant-healthcare` | Diagonal cross-hatch pattern with teal accents |
| `gradient` | `.bg-variant-gradient` | Deep navy-to-black gradient + SVG grain texture |

### Switching Variants

Edit `lib/variants.ts` and change the `DEFAULT_VARIANT` constant:

```ts
export const DEFAULT_VARIANT: BackgroundVariant = "mesh"; // "mesh" | "healthcare" | "gradient"
```

The variant class is applied to `<body>` in `app/layout.tsx`.

## Updating Content

All page copy, statistics, and URLs are centralized in `lib/constants.ts`. Edit this single file to update:

- Brand name and tagline
- Hero headline, subheadline, and CTAs
- Pain point cards (title, description, stat)
- Market and product statistics
- Calendly URL
- Footer links

No component files need to change for content updates.

## Calendly Integration

The "Book a Call" section embeds Calendly's inline widget. Update the URL in `lib/constants.ts`:

```ts
export const CALENDLY_URL = "https://calendly.com/your-org/asre-demo";
```

The widget script and stylesheet are loaded dynamically on the client side.

## Deployment

The site is configured for static export (`output: "export"` in `next.config.ts`). After `npm run build`, the `out/` directory contains the complete static site.

### Cloudflare Pages

1. Connect your repository
2. Set build command: `cd website && npm install && npm run build`
3. Set output directory: `website/out`

### Railway

1. Create a new service from the repository
2. Set root directory: `website`
3. Build command: `npm install && npm run build`
4. Static deploy from `out/`

### Vercel

1. Import the repository
2. Set root directory: `website`
3. Framework preset: Next.js (auto-detected)

## Design Tokens

| Token | Value | Usage |
|-------|-------|-------|
| Primary | `#0EA5E9` | Accent color, CTAs, highlights |
| Dark | `#0F172A` | Background base |
| Dark-50 | `#1E293B` | Card backgrounds |
| Dark-100 | `#334155` | Borders |
| Body text | `#E2E8F0` (slate-200) | Default text |
| Muted text | `#94A3B8` (slate-400) | Descriptions, subtitles |

## No External Animation Libraries

All animations use CSS `@keyframes` and the Intersection Observer API. No Framer Motion, GSAP, or other animation libraries are included, keeping the bundle under 120KB gzipped.
