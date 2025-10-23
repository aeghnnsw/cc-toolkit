#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "docling",
#   "docling-ibm-models",
#   "numpy<2",
#   "pillow",
#   "pypdfium2",
# ]
# ///
"""
Docling PDF to Markdown Split by Page - Portable Version
=========================================================
Export full markdown with proper image references, then split by pages.

This script uses inline dependencies (PEP 723) and can be run with uv:
    uv run docling_markdown_split.py input.pdf output_folder

Or with traditional Python (requires docling installed):
    python docling_markdown_split.py input.pdf output_folder
"""

import argparse
import json
import shutil
import re
from pathlib import Path
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling_core.types.doc import ImageRefMode


def split_markdown_by_page_markers(full_markdown, doc, text_folder, images_folder):
    """Split markdown by page using image markers as reliable page boundaries."""

    # Build page->content mapping directly from docling
    # Use the text attribute directly instead of export_to_text()
    page_content = {}
    for page_no in range(len(doc.pages)):
        page_items = []
        for item, level in doc.iterate_items():
            if hasattr(item, 'prov') and item.prov and len(item.prov) > 0:
                if item.prov[0].page_no == page_no:
                    # Try different ways to get text content
                    text = None
                    if hasattr(item, 'text') and item.text:
                        text = item.text
                    elif hasattr(item, 'get_text') and callable(item.get_text):
                        text = item.get_text()

                    if text and text.strip():
                        page_items.append(text.strip())
        page_content[page_no] = '\n\n'.join(page_items) if page_items else ""

    # Save each page with its content from docling plus images from full markdown
    lines = full_markdown.split('\n')

    for page_no in range(len(doc.pages)):
        content = page_content.get(page_no, "")

        # Find images for this page from full markdown
        image_lines = []
        for line in lines:
            if f'_page_{page_no + 1:03d}.png)' in line and '![Image]' in line:
                image_lines.append(line)

        # Combine content and images
        if content or image_lines:
            full_page = content
            if image_lines:
                full_page += '\n\n' + '\n'.join(image_lines)

            md_file = text_folder / f"page_{page_no + 1:03d}.md"
            md_file.write_text(full_page, encoding='utf-8')
            print(f"   ✓ Saved {md_file.name} ({len(full_page)} chars)")
        else:
            print(f"   ⚠️  Skipped page_{page_no + 1:03d}.md (no content)")


def main():
    parser = argparse.ArgumentParser(
        description='Convert PDF to markdown files split by page'
    )
    parser.add_argument('pdf_file', type=Path, help='Input PDF file')
    parser.add_argument('output_folder', type=Path, help='Output folder')
    parser.add_argument('--image-resolution-scale', type=float, default=2.0)

    args = parser.parse_args()

    if not args.pdf_file.exists():
        print(f"❌ Error: PDF file not found: {args.pdf_file}")
        return 1

    print(f"\n{'='*60}")
    print(f"📄 Docling PDF to Markdown Split by Page")
    print(f"{'='*60}")
    print(f"Input:  {args.pdf_file}")
    print(f"Output: {args.output_folder}")

    # Create output folders
    args.output_folder.mkdir(parents=True, exist_ok=True)
    text_folder = args.output_folder / "text"
    text_folder.mkdir(exist_ok=True)
    images_folder = args.output_folder / "images"
    images_folder.mkdir(exist_ok=True)

    # Configure pipeline
    pipeline_options = PdfPipelineOptions(
        images_scale=args.image_resolution_scale,
        generate_page_images=True,
        generate_picture_images=True,
    )

    print(f"\n🔄 Converting PDF...")
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )

    result = converter.convert(args.pdf_file)
    doc = result.document

    print(f"   ✓ Conversion complete!")
    print(f"   Pages: {len(doc.pages)}")

    # Export full markdown with referenced images
    print(f"\n📝 Exporting full markdown...")
    temp_md = args.output_folder / "temp_full.md"
    doc.save_as_markdown(temp_md, image_mode=ImageRefMode.REFERENCED)
    full_markdown = temp_md.read_text(encoding='utf-8')
    print(f"   ✓ Full markdown exported ({len(full_markdown)} chars)")

    # Copy and rename images
    print(f"\n🖼️  Processing images...")

    # Find artifacts folder (docling may create nested paths)
    artifacts_folder = None
    for potential_path in [
        temp_md.parent / f"{temp_md.stem}_artifacts",  # Expected path
        temp_md.parent / args.output_folder.name / f"{temp_md.stem}_artifacts",  # Nested path
    ]:
        if potential_path.exists():
            artifacts_folder = potential_path
            break

    if not artifacts_folder:
        # Search for artifacts folder recursively
        for item in args.output_folder.rglob(f"{temp_md.stem}_artifacts"):
            if item.is_dir():
                artifacts_folder = item
                break

    image_count = 0

    if artifacts_folder and artifacts_folder.exists():
        for idx, img_file in enumerate(sorted(artifacts_folder.glob("*.png")), start=1):
            # Find page for this image
            page_no = "unknown"
            for pic_idx, picture in enumerate(doc.pictures, start=1):
                if pic_idx == idx and picture.prov and len(picture.prov) > 0:
                    page_no = f"page_{picture.prov[0].page_no + 1:03d}"
                    break

            simple_name = f"image_{idx:03d}_{page_no}.png"
            shutil.copy2(img_file, images_folder / simple_name)

            # Update markdown references - try multiple path formats
            relative_artifacts = artifacts_folder.relative_to(args.output_folder)
            old_paths = [
                f"{temp_md.stem}_artifacts/{img_file.name}",  # Standard
                f"{relative_artifacts}/{img_file.name}",  # Nested path
            ]
            new_path = f"../images/{simple_name}"

            for old_path in old_paths:
                old_ref = f"]({old_path})"
                if old_ref in full_markdown:
                    full_markdown = full_markdown.replace(old_ref, f"]({new_path})")
                    break

            print(f"   ✓ Copied {simple_name}")
            image_count += 1

        shutil.rmtree(artifacts_folder)

        # Clean up empty parent folder if it exists
        parent_folder = artifacts_folder.parent
        if parent_folder != args.output_folder and parent_folder.exists():
            try:
                parent_folder.rmdir()  # Only removes if empty
            except OSError:
                pass  # Folder not empty or can't be removed

    # Split markdown by pages
    print(f"\n📄 Splitting markdown by pages...")
    split_markdown_by_page_markers(full_markdown, doc, text_folder, images_folder)

    # Clean up temp file
    if temp_md.exists():
        temp_md.unlink()

    # Export metadata
    print(f"\n📋 Exporting metadata...")
    metadata = {
        "document_name": doc.name,
        "total_pages": len(doc.pages),
        "total_images": image_count,
        "export_mode": "markdown_by_page",
    }
    (args.output_folder / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding='utf-8'
    )

    print(f"\n{'='*60}")
    print(f"✅ Complete!")
    print(f"{'='*60}")
    print(f"  📁 text/       - {len(doc.pages)} markdown files")
    print(f"  📁 images/     - {image_count} PNG images")
    print(f"  📄 metadata.json")
    print()

    return 0


if __name__ == '__main__':
    exit(main())
