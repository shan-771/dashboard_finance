# Center-Aligned Login Portal

Refine the MI FINS CRM login screen to place the portal card dead-center in the viewport horizontally and vertically, styled as a crisp bordered flat card with left-aligned internal content.

## User Review & Critical Decisions

> [!IMPORTANT]
> The following user preferences from Phase 1 are confirmed and incorporated into the design:
> - **Internal Alignment**: Centered card on screen with left-aligned internal content (clean form rhythm, easy left-edge scanning for labels, demo chips, and inputs).
> - **Container Style**: Clean bordered flat card (subtle border, minimal elevation, refined background contrast against the canvas in both light and dark themes).

- **Confirmed Decision 1**: The login shell container will utilize CSS grid/flexbox viewport centering (`min-height: 100dvh; display: grid; place-items: center; margin: 0 auto;`) ensuring robust optical centering across desktop monitors, laptops, tablets, and mobile devices.
- **Confirmed Decision 2**: The card itself maintains a crisp 1px solid border (`var(--line)`), clean 16px corner radius, zero excessive drop shadow (flat aesthetic), and standardized 36px–40px internal padding.

---

## 1. Overview & Core Concept

- **What It Does**: Centers the staff authentication portal card on the display, establishing a balanced, distraction-free gateway into the MI FINS CRM.
- **Target Audience / Persona**: Mortgage and loan officers, staff, and branch managers accessing the CRM across desktop and mobile browsers.
- **Key Value**: Eliminates visual drift, awkward top-weighted vertical alignment, or viewport displacement, creating a balanced, executive portal experience.

---

## 2. User Experience & Visual Design

- **Key User Flows**:
  1. Unauthenticated user visits the web app URL.
  2. The login portal appears centered in the viewport with the MI FINS brand badge, staff workspace title, demo account selector, and credentials form.
  3. Clicking demo account buttons ("demo.manager" or "demo.staff") autofills the inputs instantly.
  4. Submitting credentials logs the user in and transitions directly to the main dashboard.

- **Visual Identity & Theme**:
  - **Aesthetic Direction**: Corporate financial utility with calm, orderly geometry and sharp typography.
  - **Color Palette & Flat Card Styling**:
    - Light Theme Canvas: Warm neutral canvas `--bg` (`#f6f5ef`), flat card surface `--surface` (`#ffffff`), border `--line` (`#dcd9ce`).
    - Dark Theme Canvas: Deep slate canvas `--bg` (`#071a23`), card surface `--surface` (`#0c2531`), border `--line` (`#193d4c`).
    - Flat Card Treatment: `border: 1px solid var(--line); box-shadow: none;` for a minimalist, non-distracting profile.
  - **Typography & Rhythm**:
    - Brand badge: Geometric angled "M" monogram beside bold "MI FINS" branding.
    - Eyebrow: "STAFF WORKSPACE" in 12px uppercase tracking.
    - Title: "Welcome back" in 28px Manrope with comfortable line height.
    - Form Labels: Left-aligned 14px bold labels with clear input affordances and focus rings.

---

## 3. Key Product Decisions & Trade-Offs

- **Decision 1: Viewport Geometry & Centering Model**:
  - *Chosen Approach*: Use `min-height: 100dvh` and CSS grid `place-items: center` on `.login-shell` with `#root { min-height: 100dvh; width: 100%; display: flex; flex-direction: column; }`.
  - *Why*: Modern mobile browsers dynamically expand and contract address bars (`100vh` causes subtle off-center scrolling bugs on mobile devices; `100dvh` provides accurate vertical centering).
  - *Alternatives Considered*: Absolute positioning with `transform: translate(-50%, -50%)`, which breaks scrollability on small screens when virtual keyboards open.

- **Decision 2: Flat Card Aesthetics**:
  - *Chosen Approach*: Subtle 1px boundary line without heavy drop shadows (`box-shadow: 0 1px 3px rgba(0,0,0,0.04)`), matching user's selected preference.
  - *Why*: Reduces visual visual clutter and delivers an authentic, professional financial portal appearance.

---

## 4. Technical Architecture & Data Strategy

```
┌────────────────────────────────────────────────────────┐
│                   Browser Viewport                     │
│                (100dvh, flex / grid)                   │
│                                                        │
│   ┌────────────────────────────────────────────────┐   │
│   │           Centered Login Portal Card           │   │
│   │             (max-width: 460px)                 │   │
│   │                                                │   │
│   │  [M] MI FINS (Mahi Homes & Finance CRM)       │   │
│   │  STAFF WORKSPACE                               │   │
│   │  Welcome back                                  │   │
│   │  Sign in with your staff credentials...        │   │
│   │                                                │   │
│   │  ┌──────────────────────────────────────────┐  │   │
│   │  │ [Manager demo.manager] [Staff demo.staff]│  │   │
│   │  └──────────────────────────────────────────┘  │   │
│   │                                                │   │
│   │  User ID   [ demo.manager                 ]    │   │
│   │  Password  [ •••••••••••••••••••••••••••• ]    │   │
│   │                                                │   │
│   │  [             Sign In                    ]    │   │
│   │                                                │   │
│   │  Protected workspace for authorized personnel  │   │
│   └────────────────────────────────────────────────┘   │
│                                                        │
└────────────────────────────────────────────────────────┘
```

### Files to Update Upon Approval
- `src/auth.css`: Configure `.login-shell` with `min-height: 100dvh`, `width: 100%`, `display: grid`, `place-items: center`, padding `24px`. Update `.login-card` with clean flat border, zero heavy shadow, responsive max-width (`460px`), and left-aligned text and fields.
- `src/index.css`: Ensure `#root` occupies `min-height: 100dvh; width: 100%; display: flex; flex-direction: column;` to guarantee full viewport centering propagation.
