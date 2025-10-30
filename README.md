# cc-skills

Personal collection of custom Claude Code skills.

## What are Skills?

Skills are modular capabilities that extend Claude Code's functionality. They package expertise into discoverable capabilities that Claude can automatically use when relevant to your request.

## Purpose

This repository contains custom skills tailored for my personal workflows and automation needs. Skills are stored here for version control and easy synchronization across projects.

## Available Skills

### Development Skills (`dev-skills`)
- **problem-solving-cycle**: Systematic development workflow from brainstorming to PR merge, including issue creation, branch management, and cleanup
- **step-workflow**: Step-based file naming and folder organization using numbered prefixes (01_, 02_, 03_) for clear workflow order

### Creator Skills (`creator-skills`)
- **sci-figure-format**: Publication-quality scientific figure formatting for major journals
- **sci-slides**: Academic presentation slide creation for STEM fields

### Document Skills (`doc-skills`)
- **docling-pdf**: PDF to markdown conversion using IBM's Docling library

## Usage

Skills from this repository can be used as:
- **Personal skills**: Installed in `~/.claude/skills/` for all projects
- **Project skills**: Linked in specific projects under `.claude/skills/`
