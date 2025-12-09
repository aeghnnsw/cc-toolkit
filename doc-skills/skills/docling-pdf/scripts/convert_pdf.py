#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "docling",
#   "docling-ibm-models",
#   "numpy<2",
#   "pillow",
#   "pypdfium2",
#   "tabulate",
# ]
# ///
"""
Docling PDF to Markdown Converter
==================================
Convert PDF to markdown with extracted figures and tables.

Features:
- Extracts complete markdown document
- Extracts figures to figures/ folder (figure_001.png, etc.)
- Extracts tables to tables/ folder as markdown files
- Comprehensive metadata output

Usage with uv:
    uv run convert_pdf.py input.pdf output_folder [options]

Usage with Python:
    python convert_pdf.py input.pdf output_folder [options]

Options:
    --image-resolution-scale F  Image resolution scale (default: 2.0)
"""

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Tuple, List, Dict, Any

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling_core.types.doc import ImageRefMode


def setup_output_folders(output_folder: Path) -> Tuple[Path, Path]:
    """Create and return output folder structure."""
    output_folder.mkdir(parents=True, exist_ok=True)

    figures_folder = output_folder / "figures"
    figures_folder.mkdir(exist_ok=True)

    tables_folder = output_folder / "tables"
    tables_folder.mkdir(exist_ok=True)

    return figures_folder, tables_folder


def extract_figures(doc, output_folder: Path, full_md_path: Path, markdown_content: str) -> Tuple[int, str]:
    """
    Extract figures from document artifacts and update markdown references.

    Returns:
        Tuple of (figure_count, updated_markdown_content)
    """
    print(f"\n🖼️  Processing figures...")

    figures_folder = output_folder / "figures"
    stem = full_md_path.stem

    # Find artifacts folder created by docling
    artifacts_folder = None
    for potential_path in [
        full_md_path.parent / f"{stem}_artifacts",
        full_md_path.parent / output_folder.name / f"{stem}_artifacts",
    ]:
        if potential_path.exists():
            artifacts_folder = potential_path
            break

    if not artifacts_folder:
        for item in output_folder.rglob(f"{stem}_artifacts"):
            if item.is_dir():
                artifacts_folder = item
                break

    figure_count = 0

    if artifacts_folder and artifacts_folder.exists():
        for img_file in sorted(artifacts_folder.glob("*.png")):
            figure_count += 1
            figure_name = f"figure_{figure_count:03d}.png"
            shutil.copy2(img_file, figures_folder / figure_name)

            # Update markdown references
            old_ref = f"]({artifacts_folder.relative_to(output_folder)}/{img_file.name})"
            new_ref = f"](figures/{figure_name})"
            markdown_content = markdown_content.replace(old_ref, new_ref)

            # Also try absolute path reference
            old_ref_abs = f"]({stem}_artifacts/{img_file.name})"
            markdown_content = markdown_content.replace(old_ref_abs, new_ref)

            print(f"   ✓ Extracted {figure_name}")

        # Clean up artifacts folder
        shutil.rmtree(artifacts_folder)

        # Clean up empty parent if nested
        parent_folder = artifacts_folder.parent
        if parent_folder != output_folder and parent_folder.exists():
            try:
                parent_folder.rmdir()
            except OSError:
                pass

    if figure_count == 0:
        print(f"   ℹ️  No figures found in document")
    else:
        print(f"   ✓ Processed {figure_count} figures")

    return figure_count, markdown_content


def extract_tables(doc, output_folder: Path) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Extract tables from document and save as markdown files.

    Returns:
        Tuple of (table_count, table_info_list)
    """
    print(f"\n📊 Extracting tables...")

    tables_folder = output_folder / "tables"

    table_count = 0
    table_info = []

    for table_ix, table in enumerate(doc.tables, start=1):
        try:
            # Export to DataFrame
            table_df = table.export_to_dataframe()

            if table_df.empty:
                continue

            table_count += 1
            table_name = f"table_{table_count:03d}"

            # Save as Markdown
            md_path = tables_folder / f"{table_name}.md"
            md_content = table_df.to_markdown(index=False)
            md_path.write_text(md_content, encoding='utf-8')

            print(f"   ✓ Saved {table_name}.md ({len(table_df)} rows × {len(table_df.columns)} cols)")

            table_info.append({
                "name": table_name,
                "rows": len(table_df),
                "columns": len(table_df.columns),
                "path": f"tables/{table_name}.md"
            })

        except Exception as e:
            print(f"   ⚠️  Warning: Could not export table {table_ix}: {e}")
            continue

    if table_count == 0:
        print(f"   ℹ️  No tables found in document")

    return table_count, table_info


def main():
    parser = argparse.ArgumentParser(
        description='Convert PDF to markdown with figures and tables',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic conversion
  uv run convert_pdf.py paper.pdf output/

  # Higher resolution figures
  uv run convert_pdf.py paper.pdf output/ --image-resolution-scale 3.0
"""
    )

    parser.add_argument('pdf_file', type=Path, help='Input PDF file')
    parser.add_argument('output_folder', type=Path, help='Output folder')
    parser.add_argument(
        '--image-resolution-scale',
        type=float,
        default=2.0,
        help='Image resolution scale (default: 2.0)'
    )

    args = parser.parse_args()

    # Start overall timer
    start_time = time.time()

    # Validate input
    if not args.pdf_file.exists():
        print(f"❌ Error: PDF file not found: {args.pdf_file}")
        return 1

    # Print header
    print(f"\n{'='*70}")
    print(f"📄 Docling PDF to Markdown Converter (Standard Pipeline)")
    print(f"{'='*70}")
    print(f"Input:       {args.pdf_file}")
    print(f"Output:      {args.output_folder}")
    print(f"Image scale: {args.image_resolution_scale}x")

    # Setup output folders
    figures_folder, tables_folder = setup_output_folders(args.output_folder)

    # Configure PDF pipeline
    pipeline_options = PdfPipelineOptions(
        images_scale=args.image_resolution_scale,
        generate_page_images=False,      # Don't generate full page images
        generate_picture_images=True,    # Extract actual figures/images
    )

    # Convert PDF
    print(f"\n🔄 Converting PDF with docling...")
    conversion_start = time.time()

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )

    result = converter.convert(args.pdf_file)
    doc = result.document

    conversion_time = time.time() - conversion_start

    print(f"   ✓ Conversion complete! ({conversion_time:.2f}s)")
    print(f"   ✓ PDF pages: {len(doc.pages)}")

    # Export full markdown
    print(f"\n📝 Exporting full markdown...")
    full_md_path = args.output_folder / "full_document.md"
    doc.save_as_markdown(full_md_path, image_mode=ImageRefMode.REFERENCED)
    markdown_content = full_md_path.read_text(encoding='utf-8')
    print(f"   ✓ Exported ({len(markdown_content):,} chars)")

    # Extract figures and update references
    figure_count, markdown_content = extract_figures(
        doc,
        args.output_folder,
        full_md_path,
        markdown_content
    )

    # Extract tables
    table_count, table_info = extract_tables(doc, args.output_folder)

    # Save updated markdown with corrected references
    full_md_path.write_text(markdown_content, encoding='utf-8')

    # Calculate total time
    total_time = time.time() - start_time

    # Export metadata
    print(f"\n📋 Exporting metadata...")
    metadata = {
        "document_name": doc.name,
        "pdf_pages": len(doc.pages),
        "total_figures": figure_count,
        "total_tables": table_count,
        "total_chars": len(markdown_content),
        "image_resolution_scale": args.image_resolution_scale,
        "table_info": table_info,
        "pipeline": "standard",
        "timing": {
            "conversion_time": round(conversion_time, 2),
            "total_time": round(total_time, 2)
        }
    }

    metadata_path = args.output_folder / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(f"   ✓ Saved metadata.json")

    # Print summary
    print(f"\n{'='*70}")
    print(f"✅ Conversion Complete!")
    print(f"{'='*70}")
    print(f"📄 full_document.md  - Complete markdown ({len(markdown_content):,} chars)")
    print(f"📁 figures/          - {figure_count} PNG images")
    print(f"📁 tables/           - {table_count} markdown tables")
    print(f"📄 metadata.json     - Document metadata")
    print(f"\n⏱️  Timing:")
    print(f"   PDF conversion: {conversion_time:.2f}s")
    print(f"   Total time:     {total_time:.2f}s")
    print()

    return 0


if __name__ == '__main__':
    exit(main())
