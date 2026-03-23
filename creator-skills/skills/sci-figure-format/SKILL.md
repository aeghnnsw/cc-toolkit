---
name: sci-figure-format
version: 1.0.0
description: Guide for creating publication-quality scientific figures that meet major journal standards (Nature, Science, ACS, RSC). Use this skill when users ask about scientific figure formatting, journal requirements, colorblind-safe palettes, resolution/DPI, file formats, fonts, or figure dimensions for publication.
---

# Scientific Figure Formatting

Guidelines for creating publication-quality figures that meet standards of Nature, Science, ACS, and RSC journals.

---

## Universal Standards (All Major Journals)

| Element | Requirement |
|---------|-------------|
| **Colors** | Okabe-Ito palette (colorblind-safe) |
| **Font** | Helvetica or Arial, 6-8 pt |
| **Resolution** | 600 DPI minimum |
| **Format** | PDF (graphs) or TIFF (images) |
| **Width** | 3.5" (single column) or 7" (double column) |
| **Line weight** | ≥0.5 pt |

---

## 1. Color Palettes

### Okabe-Ito (Default - Categorical Data ≤8 groups)

```
#E69F00
#56B4E9
#009E73
#F0E442
#0072B2
#D55E00
#CC79A7
#999999
```

**When to use:** Line plots, bar charts, scatter plots, any categorical data

---

### ColorBrewer Set3 (9-12 categories)

```
#8DD3C7
#FFFFB3
#BEBADA
#FB8072
#80B1D3
#FDB462
#B3DE69
#FCCDE5
#D9D9D9
#BC80BD
#CCEBC5
#FFED6F
```

**When to use:** More than 8 categories needed

---

### PiYG Diverging (Data with midpoint)

```
#C51B7D
#DE77AE
#F1B6DA
#FDE0EF
#E6F5D0
#B8E186
#7FBC41
#4D9221
```

**When to use:** Correlation matrices, positive vs negative values
**Why:** Avoids red-green, colorblind-safe

---

### BuRd Diverging (Blue-Red)

```
#2166AC
#4393C3
#92C5DE
#D1E5F0
#F7F7F7
#FDDBC7
#F4A582
#D6604D
#B2182B
```

**When to use:** Temperature data, classic diverging scale

---

### Two-Color Pairs

- **Blue-Orange:** #0072B2 + #E69F00 (most versatile)
- **Green-Magenta:** #009E73 + #CC79A7
- **Cyan-Vermillion:** #56B4E9 + #D55E00

**Avoid:** Red-Green combinations (colorblind issue)

---

## 2. Typography

**Font:** Helvetica or Arial (sans-serif only)

**Sizes:**
- Axis labels: 8 pt
- Tick labels: 7 pt
- Legend: 7 pt
- Panel labels (a,b,c): 8-10 pt bold

**Minimum:** 5 pt (Nature/ACS requirement)
**Recommended:** 6-8 pt for readability

---

## 3. Resolution & File Formats

**Resolution:**
- Default: 600 DPI (exceeds all journal minimums)
- Color images: 300-600 DPI
- Line art: 600-1200 DPI

**File Formats:**
- **Graphs/charts:** PDF (vector, preferred) or EPS
- **Photos/images:** TIFF or PNG
- **Avoid:** JPEG (lossy compression)

**Key principle:** Use vector formats (PDF/EPS) for graphs - they scale without quality loss

---

## 4. Figure Dimensions

**Standard widths:**
- **Single column:** 3.5 inches (9 cm)
- **Double column:** 7 inches (18 cm)
- **Height:** ≤10 inches

**Journal-specific widths:**
- Nature: 90mm / 180mm
- Science: 3.5-7.3 inches
- ACS: 3.25" / 7"
- RSC: 8.3cm / 17.1cm

**Design at final print size** to ensure text legibility and correct proportions.

---

## 5. Design Principles

**Do:**
- Keep simple and uncluttered
- Use clear axis labels with units (e.g., "Time (s)")
- Remove unnecessary gridlines
- Maintain consistency across all figures
- Ensure line thickness ≥0.5 pt (prefer 1-1.5 pt)

**Avoid:**
- Red-green color combinations
- Rainbow colormaps
- Font sizes <5 pt
- 3D effects
- Serif fonts
- JPEG for graphs

---

## 6. Pre-Submission Checklist

**Format:**
- [ ] 600 DPI minimum resolution
- [ ] Vector format with editable text

**Typography:**
- [ ] Helvetica or Arial used
- [ ] Font size ≥6 pt
- [ ] Consistent font across all figures

**Dimensions:**
- [ ] Width: 3.5" (single) or 7" (double)
- [ ] Height ≤10 inches
- [ ] Designed at final size

**Colors:**
- [ ] Colorblind-safe palette (Okabe-Ito)
- [ ] No red-green combinations

**Design:**
- [ ] Clear axis labels with units
- [ ] Line thickness ≥0.5 pt
- [ ] No unnecessary decoration
- [ ] Consistent style
---

## Workflow

When helping users format figures:

1. **Select color palette:**
   - ≤8 categories → Okabe-Ito
   - 9-12 categories → Set3
   - Diverging data → PiYG or BuRd
   - 2 colors → Blue-Orange
2. **Apply standards:**
   - Font: Helvetica/Arial, 6-8 pt
   - Resolution: 600 DPI
   - Width: 3.5" or 7"
   - Format: PDF (graphs) or TIFF (images)
3. **Verify design:**
   - Simple, clear layout
   - Labels with units
   - Line weights ≥0.5 pt

---