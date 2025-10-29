---
name: docling-pdf
description: Convert PDF documents to AI-accessible markdown format using IBM's Docling library. This skill should be used when the user needs to extract content from PDFs including text, figures, and tables in a structured markdown format. It handles scientific papers, technical documents, reports, and any PDF requiring content extraction for AI processing or analysis.
---

# Docling PDF Converter

## Overview

Convert PDF documents to structured markdown using IBM's Docling library. Extract complete document content including text, figures (as PNG files), and tables (as separate markdown files) in an AI-accessible format optimized for further processing and analysis.

## When to Use This Skill

Use this skill when the user needs to:
- Convert PDFs to markdown for AI analysis
- Extract figures and tables from research papers or technical documents
- Process PDF content for documentation or knowledge base purposes
- Analyze document structure and content programmatically
- Extract text from complex PDFs while preserving formatting

## Quick Start

Convert a PDF using the bundled script:

```bash
uv run --python 3.10 scripts/convert_pdf.py input.pdf output_folder
```

This produces:
- `full_document.md` - Complete markdown with cleaned references
- `figures/` - Numbered PNG files (figure_001.png, figure_002.png, etc.)
- `tables/` - Individual markdown tables (table_001.md, table_002.md, etc.)
- `metadata.json` - Document statistics and conversion timing

## Conversion Process

### Step 1: Prepare the Environment

The script uses `uv` to manage dependencies automatically. No manual installation required. The script's inline metadata specifies all required packages.

### Step 2: Execute Conversion

Run the conversion script with the following syntax:

```bash
uv run --python 3.10 scripts/convert_pdf.py <pdf_file> <output_folder> [options]
```

**Required arguments:**
- `pdf_file` - Path to the input PDF file
- `output_folder` - Directory where output will be saved

**Optional arguments:**
- `--image-resolution-scale F` - Scale factor for extracted images (default: 2.0)

**Examples:**

```bash
# Basic conversion
uv run --python 3.10 scripts/convert_pdf.py paper.pdf output/

```

### Step 3: Process Output

The conversion creates a structured output directory:

```
output_folder/
├── full_document.md     # Complete markdown (cleaned references)
├── figures/             # PNG images
│   ├── figure_001.png
│   ├── figure_002.png
│   └── ...
├── tables/              # Markdown tables
│   ├── table_001.md
│   ├── table_002.md
│   └── ...
└── metadata.json        # Conversion statistics
```

**Key features:**
- Figure references in markdown are automatically updated to point to `figures/` directory
- Tables are exported as DataFrames converted to markdown format
- Original artifacts folders are cleaned up automatically
- Metadata includes page count, timing, figure/table counts


## Script Details

The `scripts/convert_pdf.py` script is a standalone Python script with inline dependencies that:

**Important:** The script is designed to be run with `uv run` which handles environment creation and dependency management automatically. Do not try to run it directly with `python3` without first installing dependencies.
