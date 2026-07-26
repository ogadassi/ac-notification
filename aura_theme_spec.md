# 🌌 Aura Dynamic Obsidian-Glass Design System
> **Official AI Agent & Developer Specification**  
> *Version 2.5 | Liquid Glass iOS 27 Architecture & Dynamic System Integration*

---

## 📐 Design Philosophy & Architecture

The **Aura Dynamic Obsidian-Glass** design system is engineered for modern Android applications and companion web views. 

### 🎯 Primary Intent: Android System Theme Integration
The core design intention is for the application to **dynamically inherit and derive its color scheme from the user's Android System Theme** (Material You / Dynamic System Palette `MaterialTheme.colorScheme`).
* **Primary Accent**: Derived from System `primary` / `secondary` dynamic color tokens.
* **Liquid Glass Containers (iOS 27 Spec)**: Ultra-translucent glass containers (`rgba(255, 255, 255, 0.04)`) with high-depth backdrop blur (`backdrop-filter: blur(24px)`), subtle glowing border outlines (`1px solid rgba(255, 255, 255, 0.15)`), and ambient luminous drop shadows (`shadow-[0_10px_38px_rgba(0,0,0,0.5),0_0_20px_rgba(93,230,255,0.12)]`).
* **Status Bars & Edge-to-Edge**: System status and navigation bars are set to `TRANSPARENT` so ambient radial background glow spans edge-to-edge.

### 🛡️ Default Backup Theme (Obsidian Dark Fallback)
When dynamic Android system colors are disabled, uninitialized, or running on non-Android standalone web environments, the application **falls back to the hardcoded Obsidian Dark Palette** (`#050B14` Midnight Blue, `#5DE6FF` Neon Cyan, `#BEC6E0` Cyber Slate).

---

## 🎨 Theme Tokens & Glass Container Specs

### Core Color Tokens
| Token Name | Android System Mapping | Hardcoded Fallback (Default) | Role / Usage |
|---|---|---|---|
| `--background` | `colorScheme.background` | `#050B14` | Primary dark canvas background |
| `--surface-container` | `colorScheme.surfaceContainer` | `rgba(18, 30, 49, 0.4)` / `#122131` | Glassmorphic card surface background |
| `--surface-container-high` | `colorScheme.surfaceContainerHigh` | `#1C2B3C` | Highlighted/active card surface |
| `--primary` | `colorScheme.primary` | `#BEC6E0` | Cyber Slate — primary brand color & buttons |
| `--secondary` | `colorScheme.secondary` | `#5DE6FF` | Neon Cyan — vibrant accents, active toggles, icons |
| `--tertiary` | `colorScheme.tertiary` | `#F9BD22` | Amber Gold — warning badges, secondary actions |
| `--active / success` | Custom / Green | `#4CD964` | Emerald Green — online states, active geofence |
| `--error` | `colorScheme.error` | `#FFB4AB` | Soft Coral Red — errors, disconnected states |

### 💎 Liquid Glass iOS 27 Container & Floating Pill Specification
Floating notification pills, modals, and bento cards MUST adhere to this CSS structure:
```css
.liquid-glass-pill {
    background: rgba(255, 255, 255, 0.04);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    border: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 9999px; /* Pill Shape */
    box-shadow: 0 10px 38px rgba(0, 0, 0, 0.5), 0 0 20px rgba(93, 230, 255, 0.12);
}
```

---

## 🔤 Typography Hierarchy

### Font Families
- **Display & Headings**: `Geist`, sans-serif
- **Body & Controls**: `Inter`, sans-serif
- **Status & Numbers**: `Geist`, monospace / tabular figures

---

## 📱 Android & Server Integration Rules

1. **Payload Strictness**:
   - Server endpoints (`/api/v1/ac/trigger`) accept both `action: "ac_on"` and `action: "ac_off"` payloads smoothly without strict key enforcement throwing 400 errors.
2. **Ground-Truth Hardware Sync**:
   - All UI compartments (Home State Card, Top-Left Logo Button, Notification Pills) sync atomically with verified live server responses (`GET /api/v1/ac/status`).
