# Logo Standard

## Canonical Definition

The Suzent logo is a **black rounded square with two white rectangular eyes** — a minimal neo-brutalist face.

**Single source of truth: [`frontend/src/components/SuzentLogo.tsx`](../../frontend/src/components/SuzentLogo.tsx)**

All UI placements use this component. The static asset [`frontend/public/favicon.svg`](../../frontend/public/favicon.svg) mirrors the same geometry for browser favicon and OS-level use; it is **not** the source — `SuzentLogo.tsx` is.

### Geometry (SVG viewBox `0 0 24 24`)

| Element | x | y | width | height | rx | fill |
|---------|---|---|-------|--------|----|------|
| Background | 0 | 0 | 24 | 24 | 4 | `#000000` |
| Left eye | 5 | 8 | 5 | 5 | 1.5 | `#FFFFFF` |
| Right eye | 14 | 8 | 5 | 5 | 1.5 | `#FFFFFF` |

Do not alter these values. Any visual change to the logo must be made in `SuzentLogo.tsx` first, then `favicon.svg` updated to match.

## Usage

```tsx
import { SuzentLogo } from '@/components/SuzentLogo';

// Static
<SuzentLogo className="h-7 w-7" />

// Interactive — eyes follow the cursor within the SVG bounds
<SuzentLogo className="h-7 w-7" interactive />
```

### Props

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `className` | `string` | `''` | Tailwind / CSS classes (controls size and spacing) |
| `interactive` | `boolean` | `false` | Eyes track the cursor within ±1.5 SVG units. Pure event-driven CSS transform — no animation loop. |

### Sizing guidance

| Context | Recommended size |
|---------|-----------------|
| Sidebar header (h-12 bar) | `h-7 w-7` (28 px) |
| Collapsed sidebar toggle | `h-7 w-7` (28 px) |
| Splash / onboarding screen | `h-16 w-16` or larger |
| Favicon / OS icon | Use `favicon.svg` directly |

## What NOT to do

- Do not inline the SVG in component files — always import `SuzentLogo`.
- Do not add a white outer border or additional wrapper rectangles (this was the pre-DRY bug).
- Do not change the eye coordinates or background color without updating `favicon.svg` in the same commit.
- Do not use `interactive` in contexts where the component may render hundreds of times (e.g. inside a list row).

## RobotAvatar relationship

[`RobotAvatar`](../../frontend/src/components/chat/RobotAvatar.tsx) internally defines a `RobotFace` primitive with identical geometry. This is intentional: `RobotAvatar` is a self-contained animation system with per-variant eye transforms (`eyesClass`, `eyeStyle`) that would be complicated to route through `SuzentLogo`. The two definitions must stay geometrically in sync; if you update the logo geometry, update `RobotFace` as well.
