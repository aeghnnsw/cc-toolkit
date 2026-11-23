---
name: sci-figure-format
description: Use when creating or reviewing scientific figures for publication, including journal dimensions, resolution, file formats, typography, line weights, colorblind-safe palettes, and Nature, Science, ACS, or RSC requirements.
---

# Scientific Figure Formatting

Guidelines for creating publication-quality figures that meet standards of Nature, Science, ACS, and RSC journals.

---

## Universal Standards (All Major Journals)

This table gives the one value of each rule. The other sections refer to it.

| Element | Requirement |
|---------|-------------|
| **Colors** | Okabe-Ito palette (colorblind-safe) |
| **Font** | Helvetica or Arial; 6-8 pt target, 5 pt hard minimum (Nature/ACS requirement); panel labels (a, b, c) 8-10 pt bold |
| **Resolution** | At the final print size: 300 DPI minimum for photos; 600 DPI minimum for line art and for combination figures (photos with lines or text). Use the journal's value when it asks for more |
| **Format** | PDF (vector, preferred) or EPS for graphs; TIFF for photos and other raster images; no JPEG (lossy compression) |
| **Width** | 3.5" (9 cm, single column) or 7" (18 cm, double column). Use the target journal's width when the journal gives one |
| **Height** | ≤10" |
| **Line weight** | ≥0.5 pt; 1-1.5 pt preferred |

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

### Soft Okabe-Ito (Muted Categorical Data ≤8 groups)

```
#C6A15B
#8EACB8
#83A08E
#C8BC7B
#6E8EA0
#BC7A62
#AC8B9D
#A29E97
```

**When to use:** Low-saturation editorial figures where a soft, Morandi-inspired appearance is preferred

**Accessibility note:** Muting reduces contrast and category separability. Pair colors with shapes, markers, or line styles; verify them against the final background. Use the original Okabe-Ito palette when accessibility is the priority.

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

**Font and size limits:** the Font row of [Universal Standards](#universal-standards-all-major-journals). Use sans-serif fonts only.

**Sizes:**
- Axis labels: 8 pt
- Tick labels: 7 pt
- Legend: 7 pt

---

## 3. Resolution & File Formats

**Resolution and file formats:** the Resolution and Format rows of [Universal Standards](#universal-standards-all-major-journals).

**Key principle:** vector formats scale without quality loss, so the Format row prefers them for graphs.

---

## 4. Figure Dimensions

**Standard width and height:** the Width and Height rows of [Universal Standards](#universal-standards-all-major-journals).

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
- Keep line weights within the Line weight row of [Universal Standards](#universal-standards-all-major-journals)

**Avoid:**
- Red-green color combinations
- Rainbow colormaps
- Text below the minimum of the Font row
- 3D effects
- Serif fonts
- JPEG files

---

## 6. Pre-Submission Checklist

Each row that an item names is a row of [Universal Standards](#universal-standards-all-major-journals).

**Format:**
- [ ] Resolution meets the Resolution row
- [ ] File format meets the Format row
- [ ] Vector format with editable text

**Typography:**
- [ ] Font and sizes meet the Font row
- [ ] Consistent font across all figures

**Dimensions:**
- [ ] Width and height meet the Width and Height rows
- [ ] Designed at final size

**Colors:**
- [ ] Colorblind-safe palette (Okabe-Ito)
- [ ] No red-green combinations
- [ ] Soft Okabe-Ito, when used, is paired with shapes, markers, or line styles and checked against the final background

**Design:**
- [ ] Clear axis labels with units
- [ ] Line weights meet the Line weight row
- [ ] No unnecessary decoration
- [ ] Consistent style
---

## Workflow

When helping users format figures:

1. **Select color palette:**
   - ≤8 categories → Okabe-Ito
   - ≤8 categories with a muted editorial style → Soft Okabe-Ito with redundant shape, marker, or line-style encoding
   - 9-12 categories → Set3
   - Diverging data → PiYG or BuRd
   - 2 colors → Blue-Orange
2. **Apply standards:** apply each row of [Universal Standards](#universal-standards-all-major-journals): font, resolution, format, width, height, and line weight.
3. **Verify design:**
   - Simple, clear layout
   - Labels with units

---
