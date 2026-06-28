---
name: Luminous Equity
colors:
  surface: '#f7f9fb'
  surface-dim: '#d8dadc'
  surface-bright: '#f7f9fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f4f6'
  surface-container: '#eceef0'
  surface-container-high: '#e6e8ea'
  surface-container-highest: '#e0e3e5'
  on-surface: '#191c1e'
  on-surface-variant: '#3c4a43'
  inverse-surface: '#2d3133'
  inverse-on-surface: '#eff1f3'
  outline: '#6b7b72'
  outline-variant: '#bacac1'
  surface-tint: '#006c4f'
  primary: '#006c4f'
  on-primary: '#ffffff'
  primary-container: '#00d09c'
  on-primary-container: '#00533c'
  inverse-primary: '#2fe0aa'
  secondary: '#565e74'
  on-secondary: '#ffffff'
  secondary-container: '#dae2fd'
  on-secondary-container: '#5c647a'
  tertiary: '#505f76'
  on-tertiary: '#ffffff'
  tertiary-container: '#a8b9d2'
  on-tertiary-container: '#3a495f'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#59fdc5'
  primary-fixed-dim: '#2fe0aa'
  on-primary-fixed: '#002116'
  on-primary-fixed-variant: '#00513b'
  secondary-fixed: '#dae2fd'
  secondary-fixed-dim: '#bec6e0'
  on-secondary-fixed: '#131b2e'
  on-secondary-fixed-variant: '#3f465c'
  tertiary-fixed: '#d3e4fe'
  tertiary-fixed-dim: '#b7c8e1'
  on-tertiary-fixed: '#0b1c30'
  on-tertiary-fixed-variant: '#38485d'
  background: '#f7f9fb'
  on-background: '#191c1e'
  surface-variant: '#e0e3e5'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: '1.1'
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '500'
    lineHeight: '1.3'
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.6'
    letterSpacing: '0'
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
    letterSpacing: '0'
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: '1'
    letterSpacing: 0.08em
  label-sm:
    fontFamily: Inter
    fontSize: 10px
    fontWeight: '700'
    lineHeight: '1'
    letterSpacing: 0.1em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 4px
  container-padding-mobile: 1rem
  container-padding-desktop: 2.5rem
  gutter: 1.5rem
  section-gap: 4rem
---

## Brand & Style
This design system embodies the "Ultra-Premium Fintech" ethos, balancing institutional trust with cutting-edge digital craftsmanship. The aesthetic is defined by **Luminous Glassmorphism**—a style that favors transparency, light refraction, and depth over solid surfaces. 

The target audience is the sophisticated investor who values clarity and precision. The emotional response should be one of "calm confidence." We achieve this through a minimalist framework enriched by high-fidelity textures: frosted glass panels, hairline strokes, and soft atmospheric gradients that suggest a limitless, high-end environment.

## Colors
The palette is rooted in a pristine white and slate foundation to allow the glass effects to shine. 

- **Primary Green (#00D09C):** Used strictly for high-intent actions, success states, and critical "growth" indicators. It is a precise surgical tool, never a dominant background fill.
- **Surface Strategy:** The "Luminous" effect is created by a background layer of soft mesh gradients (Mint and Cyan bleeds) at 2-5% opacity, over which frosted glass containers sit.
- **Functional Grays:** Slate tones are used for text hierarchy to maintain a high-contrast, premium feel without the harshness of pure black.

## Typography
We utilize **Inter** for its geometric neutrality and exceptional legibility in data-dense environments. 

To achieve the premium feel:
- **High-Contrast Weights:** Jump from `400` for body text to `600/700` for headings to create clear visual anchors.
- **Letter Spacing:** Labels and small caps utilize generous tracking (8-10%) to evoke a luxury editorial feel.
- **Tight Headings:** Large display type features slightly negative letter spacing to feel "locked" and authoritative.

## Layout & Spacing
The layout follows a **Fixed Grid** philosophy on desktop (12 columns, 1200px max-width) to maintain a centered, gallery-like focus. 

- **Generous Whitespace:** Components are given ample breathing room to prevent the "cluttered" look common in finance.
- **Rhythm:** An 8px linear scale is used for all internal component spacing, while section-level spacing uses a 16px scale to ensure clear separation of concerns.
- **Mobile:** Transition to a fluid 4-column grid with 16px side margins.

## Elevation & Depth
Depth is not communicated through traditional heavy shadows, but through **optical transparency and layering**.

1.  **Backdrop Blur:** All elevated surfaces must use a `20px to 40px` backdrop-blur.
2.  **Translucency:** Surfaces use a white fill at `70% to 85%` opacity.
3.  **Hairline Strokes:** Instead of shadows, use a `1px` inner border. On the top/left, use `white (40% opacity)`; on the bottom/right, use a slightly darker `neutral (10% opacity)` to simulate a light source from the top-left.
4.  **Luminous Glow:** Active cards may feature a very soft, low-opacity outer glow matching the primary green, rather than a black shadow.

## Shapes
A "Rounded" approach balances the technical nature of fintech with a modern, approachable feel. 

- **Standard Radius:** 8px (`0.5rem`) for inputs and small cards.
- **Large Radius:** 16px (`1rem`) for primary glass containers.
- **Buttons:** Use a consistent 8px radius; avoid full-pill shapes to maintain a more structured, professional "pro-tool" appearance.

## Components
- **Glass Cards:** The primary container. White 80% opacity, 20px blur, 1px subtle white border. 
- **Primary Buttons:** Solid `#00D09C` with white text. On hover, apply a slight scale (1.02x) and a subtle increase in glow—avoid heavy color shifts.
- **Secondary Buttons:** Ghost style with a 1px slate-200 border. On hover, the background fills with a 5% slate tint.
- **Input Fields:** Minimalist design with only a bottom border (1px). Upon focus, the border transitions to Primary Green and a soft glass background appears behind the input area.
- **Chips/Tags:** Small, high-letter-spacing labels with a light 10% primary green tint and no border.
- **Tactile Feedback:** All interactive elements should use a `spring` transition (approx 300ms) for scale and blur effects to feel physical and responsive.
- **Data Visualization:** Line charts should use a 2px stroke width with a soft gradient fill beneath the line, fading to 0% opacity.