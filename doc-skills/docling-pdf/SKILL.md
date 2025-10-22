---
name: docling-pdf
description: Convert PDF files to markdown split by page for AI agent accessibility. This skill should be used when users need to convert PDFs into AI-readable format with separate markdown files per page and images as individual PNG files for efficient processing and navigation.
---

# Docling PDF to Markdown Converter

## Purpose

Convert PDF documents into an AI-accessible format with markdown files split by page and images extracted as separate PNG files. This structure enables AI agents to efficiently read, navigate, and process PDF content without loading entire documents into context.

## When to Use

Use this skill when users request:
- Converting PDFs for AI agent processing and analysis
- Making PDF content accessible to AI without context limitations
- Extracting PDF content with organized, AI-readable structure
- Enabling page-by-page navigation of large PDF documents
- Separating PDF images for individual AI processing

## Output Structure

The conversion produces a clean folder structure:

```
output_folder/
├── text/              # Markdown files (one per page)
│   ├── page_001.md
│   ├── page_002.md
│   └── ...
├── images/            # PNG images (extracted from PDF)
│   ├── image_001_page_002.png
│   ├── image_002_page_002.png
│   └── ...
└── metadata.json      # Document metadata
```

## How to Use

### Installation Requirement

This skill requires `uv` to be installed. Check if uv is available:

```bash
which uv
```

If not installed, guide the user to install it:
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or using pip
pip install uv
```

### Running the Conversion

Execute the script using `uv run` from the skill's `scripts/` directory:

```bash
uv run scripts/docling_markdown_split.py <input.pdf> <output_folder>
```

**Parameters:**
- `<input.pdf>` - Path to the PDF file to convert
- `<output_folder>` - Directory where output will be created
- `--image-resolution-scale <float>` - Optional: Image resolution (default: 2.0)

**Example:**
```bash
uv run scripts/docling_markdown_split.py document.pdf converted_output
```

**With higher resolution images:**
```bash
uv run scripts/docling_markdown_split.py document.pdf output --image-resolution-scale 3.0
```

### What the Script Does

1. Automatically installs docling and dependencies (first run only)
2. Converts the PDF using docling's document converter
3. Exports full markdown with proper image references
4. Extracts images as separate PNG files
5. Splits the markdown content by page
6. Updates image paths to reference the images folder
7. Creates metadata.json with document information

### Key Features

- **AI-optimized structure** - Page-by-page format prevents context overflow
- **No manual installation** - `uv run` handles dependencies automatically
- **Selective page access** - AI agents can read specific pages without loading entire document
- **Separate image files** - Images stored as PNG for individual processing, not base64 embedded
- **Proper image references** - Markdown uses `![Image](../images/image_XXX_page_YYY.png)` format
- **Named images** - Image filenames indicate source page number for easy reference
- **Metadata tracking** - JSON file with page count and image count

## Workflow

When a user requests PDF conversion:

1. Verify the PDF file path exists
2. Check if uv is installed (see Installation Requirement above)
3. Ask user for output folder name (or suggest based on PDF name)
4. Execute the conversion using `uv run` with the script path
5. Present the output folder structure to the user
6. If needed, read specific page markdown files to show results

## Notes

- First run downloads docling and dependencies automatically (may take time)
- Subsequent runs use cached dependencies (fast)
- The script handles multi-page PDFs automatically
- Images are extracted at 2x resolution by default for quality
- Large PDFs may take time to process (docling downloads models on first run)
- Output folder is created if it doesn't exist
