---
name: paper-rename
version: 1.0.0
description: Intelligently rename research paper PDFs from generic filenames (DOIs, serial numbers) to descriptive names based on extracted titles and metadata. This skill should be used when the user has downloaded research articles with non-descriptive filenames and wants to organize them with meaningful names based on the document content.
---

# Paper Rename

## Overview

Rename research paper PDFs from generic filenames to descriptive, meaningful names by extracting title and metadata from the document content. This skill uses `pdftotext` for efficient text extraction (first 50 lines only) without loading entire PDFs into context.

## When to Use This Skill

Use this skill when the user needs to:
- Rename a single PDF with a non-descriptive filename (DOI, serial number, download ID)
- Batch rename multiple research papers in a directory
- Organize downloaded papers with meaningful filenames
- Extract title and metadata to create descriptive filenames
- Rename papers to include specific information (author, year, topic) based on user request

## Workflow

### Step 1: Identify Target Files

Determine which PDF files need renaming:
- Single file specified by user
- Multiple files in a directory (use `ls` or `find` to list PDFs)
- Files matching a pattern

### Step 2: Extract Text Content

For each PDF, extract the first 50 lines using `pdftotext`:

```bash
pdftotext -f 1 -l 1 "input.pdf" - | head -50
```

**Command breakdown:**
- `-f 1 -l 1`: Extract only first page
- `-`: Output to stdout (not a file)
- `| head -50`: Limit to first 50 lines

### Step 3: Analyze Extracted Content

From the extracted text, identify:

1. **Title** (primary focus)
   - Usually the first prominent text block
   - May span multiple lines
   - Often in larger font/bold (pdftotext shows as plain text, so use position/length heuristics)
   - Typically appears before author names

2. **Authors** (if requested by user)
   - Usually appears after title
   - May be formatted as "FirstName LastName" or "LastName, FirstName"
   - For filename, use first author's last name only


3. **Keywords/Topic** (if requested by user)
   - May appear in abstract or keywords section
   - Use user's description if they provide topic context

### Step 4: Construct New Filename

Create a descriptive filename following these principles:

**Default format (title only):**
```
Clean_Title_Here.pdf
```

**Name with prefix**
```
Prefix_Clean_Title_Here.pdf
```

**Filename cleaning rules:**
- Replace spaces with underscores
- Remove special characters: `/ \ : * ? " < > |`
- Limit length to 100-150 characters maximum
- Remove leading/trailing whitespace and underscores
- Preserve alphanumeric characters and basic punctuation (hyphens, underscores)
- Capitalize first letter of each word for readability

**Examples:**
```
Original: s41586-023-06824-w.pdf
New: Quantum_Error_Correction_Using_Surface_Codes.pdf

Original: 10.1038_nature12345.pdf
New: 001_Neural_Networks_for_Protein_Folding.pdf

Original: download_8472839.pdf
New: Machine_Learning_in_Climate_Modeling.pdf
```

### Step 5: Perform Rename Operation

Execute the rename using `mv` command:

```bash
mv "original_filename.pdf" "New_Descriptive_Filename.pdf"
```

**Safety checks before renaming:**
- Verify new filename doesn't already exist (check with `ls` or test `[ -f "filename" ]`)
- If collision exists, append suffix: `_2.pdf`, `_3.pdf`, etc.
- Confirm the extracted title makes sense (not garbled text or metadata)

### Step 6: Batch Processing (Multiple Files)

For multiple PDFs in a directory:

1. List all PDF files: `find . -name "*.pdf" -type f`
2. Process each file sequentially
3. Handle errors gracefully (skip files that can't be processed)
4. Summarize results at the end

## User Interaction Patterns

### Pattern 1: Simple Rename Request
```
User: "Rename this PDF to something meaningful"
Action: Extract title, clean filename, rename
```

### Pattern 2: Batch Rename with Context
```
User: "Organize my downloaded papers in the Downloads folder"
Action: List PDFs, extract titles for each, rename all with progress updates
```

### Pattern 3: Custom Format Request
```
User: "Rename this to include the first author and year"
Action: Extract title, author, year; construct filename with requested format
```

### Pattern 4: Targeted Information
```
User: "Rename these PDFs but keep the filenames short, just the main topic"
Action: Extract title, identify core topic/subject, create concise filename
```

## Error Handling

Handle these common issues gracefully:

1. **pdftotext not installed**
   - Check with `which pdftotext`
   - Inform user to install: `brew install poppler` (macOS) or `apt-get install poppler-utils` (Linux)


3. **Title not clearly identifiable**
   - Extract descriptive info from first 50 lines
