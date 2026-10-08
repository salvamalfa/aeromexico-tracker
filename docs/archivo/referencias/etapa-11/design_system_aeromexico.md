# Design System — Aeroméxico Data Visual

## Design Tokens

### Colors
| Token | Value | Usage |
|-------|-------|-------|
| `--brand-azul` | #003087 | Primary brand, headers |
| `--brand-rojo` | #E31C23 | Accent, alerts, highlights |
| `--sky-deep` | #020B18 | Dark background base |
| `--sky-mid` | #071628 | Card backgrounds |
| `--sky-glow` | #0A2444 | Elevated surfaces |
| `--cloud-100` | rgba(255,255,255,0.06) | Subtle borders |
| `--cloud-200` | rgba(255,255,255,0.12) | Card borders |
| `--star-gold` | #F5C518 | KPI highlights, record values |
| `--altitude-green` | #00C896 | Positive margin, growth |
| `--altitude-amber` | #FF9F1C | Volume / load factor |
| `--text-primary` | #F0F4FF | Main text on dark |
| `--text-secondary` | #7B9BC8 | Supporting labels |
| `--text-muted` | #3D5A7A | Disabled / metadata |

### Typography Scale
| Token | Value | Usage |
|-------|-------|-------|
| `--font-display` | 'Inter', sans-serif | All text |
| `--size-hero` | clamp(40px, 6vw, 72px) | Big KPI numbers |
| `--size-heading` | 20px / 700 | Section titles |
| `--size-label` | 11px / 600 / uppercase + ls | Data labels |
| `--size-body` | 13px / 400 | Body copy |
| `--size-micro` | 10px / 400 | Footnotes |

### Spacing
| Token | Value |
|-------|-------|
| `--space-xs` | 4px |
| `--space-sm` | 8px |
| `--space-md` | 16px |
| `--space-lg` | 24px |
| `--space-xl` | 40px |
| `--space-2xl` | 64px |

### Border Radius
| Token | Value |
|-------|-------|
| `--radius-sm` | 8px |
| `--radius-md` | 16px |
| `--radius-lg` | 24px |
| `--radius-pill` | 999px |

### Shadows / Glows
| Token | Value |
|-------|-------|
| `--glow-azul` | 0 0 40px rgba(0,80,200,0.3) |
| `--glow-rojo` | 0 0 20px rgba(227,28,35,0.25) |
| `--glow-gold` | 0 0 20px rgba(245,197,24,0.3) |
| `--shadow-card` | 0 4px 24px rgba(0,0,0,0.4) |

### Motion
| Token | Value |
|-------|-------|
| `--ease-out` | cubic-bezier(0.16, 1, 0.3, 1) |
| `--ease-spring` | cubic-bezier(0.34, 1.56, 0.64, 1) |
| `--duration-fast` | 200ms |
| `--duration-normal` | 400ms |
| `--duration-slow` | 800ms |

## Component Inventory
- `HeroKPI` — Large animated metric card
- `SparkBar` — Compact bar chart inline
- `TrendLine` — Animated SVG line chart
- `StatChip` — Small pill badge with icon
- `TimelineRow` — Horizontal year-quarter timeline
- `GlowCard` — Glassmorphism data card with border glow
- `SectionDivider` — Animated horizontal rule

## Visual Language
**Concept**: "Altitude" — as Aeroméxico rose from Capítulo 11 to record profitability, 
we visualize data as an ascent through sky layers. Deep night sky at bottom (2021 losses), 
breaking through clouds mid-chart (2022 breakeven), and clear blue sky at top (2024–2025 records).

**Motion principle**: Numbers count up on scroll. Charts animate as if "taking off."
**Texture**: Subtle star field in background. Gradient horizon line separating years.
