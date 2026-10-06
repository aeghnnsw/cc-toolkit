---
name: sci-slides
version: 1.1.0
description: Use when creating, revising, or reviewing slides for an academic or STEM talk (conference talk, lab meeting, thesis defence, or journal club), including the talk's story and length, slide titles, claims about data, reused figures, and slide design.
---

# Scientific Presentation Slides

Build each slide as an assertion and its evidence: a one-line title states the
slide's finding, and the slide shows the data behind it. The audience hears the
speaker and sees only the screen, so every word on a slide must decode from
what is on screen and what the audience already knows.

## Rule sources

Apply the rules in this order. An earlier source wins a conflict.

1. The user's request in this conversation.
2. The standing rules in the project's `slide-rules.md`.
3. The template the user supplies: layouts, footer, logo, fonts, and colours.
4. This skill's defaults: [slide text](references/slide-text.md) and
   [design](references/design.md).

## Workflow

To create or revise a deck, run steps 1–5. To review an existing deck, run
step 1, set the slide budget as in step 2, run step 4 on each section, and then
run step 5.

### 1. Load the standing rules and the brief

Look for `slide-rules.md` in the deck's directory, then in each parent
directory up to the project root, and read the first one that you find. Collect
the brief:

- Slot length and Q&A time.
- Audience: field, level, and what they already know.
- The talk's question and its 2–5 messages.
- The template, if any.
- The sources: papers, data, and figures that the talk reports.

Ask the user for all missing items in one question. When no `slide-rules.md`
exists, add to that question: which standing rules apply to all of this
presenter's decks (template, wording to avoid, label and number conventions,
notes style). Save the answers to `slide-rules.md` at the project root under
the headings Template, Wording, Labels, and Notes. Keep standing rules in that
file only, and add each new standing rule that the user states later. When the
user cannot answer, record an assumption for each missing item and report it.

Done when: each brief item has a value or a recorded assumption, and the
standing rules are loaded or saved.

### 2. Plan the story and the slide budget

Set the slide budget to about one content slide per speaking minute. Speaking
time is the slot minus Q&A; when the Q&A time is unknown, assume 20% of the
slot. Title and backup slides do not count against the budget.

Write the slide list by the [story rules](references/slide-text.md#story), with
a draft assertion title for each slide.

Done when: the content slide count is within the budget, each slide has a draft
title, and each message has at least one slide of evidence.

### 3. Draft one section

Draft the next section. Apply every rule in [slide text](references/slide-text.md)
and [design](references/design.md), and follow the template. Put the spoken
detail in the notes.

Done when: each slide in the section has its title, evidence, definitions,
sources, and notes.

### 4. Review the section

Review the section that you drafted before you draft the next one. Read each
slide as an audience member who sees only that slide and the slides before it.
Run these passes on each slide, and record each finding with its slide, rule,
and fix:

1. **Meaning review.** For each title and sentence, name the quantity behind
   it and apply [claims and evidence](references/slide-text.md#claims-and-evidence).
   Check that the title claims only what the slide shows, and check each number
   against its source.
2. **Definitions.** List each term, abbreviation, dataset name, and figure
   marker, and apply [definitions](references/slide-text.md#definitions).
3. **Figures.** Apply [figures and schematics](references/slide-text.md#figures-and-schematics)
   to each reused figure and schematic.
4. **Wording.** Apply [wording](references/slide-text.md#wording) to each word.
5. **Form.** Apply [titles](references/slide-text.md#titles),
   [notes and numbers](references/slide-text.md#notes-and-numbers), the
   [design rules](references/design.md), the template, and each standing rule.

Fix each finding, then run the passes again on the slides that you changed.
Report a finding that needs the user's input, such as a missing source or an
unknown threshold, instead of guessing.

Done when: each slide in the section passes all five passes, or its open
findings are in the report for the user.

Repeat steps 3 and 4 until every section is drafted and reviewed.

### 5. Review the deck

- **Story:** the deck follows the [story rules](references/slide-text.md#story),
  and each message has its evidence.
- **Budget:** the content slide count is within the slide budget.
- **Terms:** each concept has one term across all sections, defined at its
  first use.
- **Layout:** when a renderer is available, render the deck and inspect each
  slide: each title fits one line, no text overflows, and each label is
  readable. Otherwise, report that the layout was not checked.

Fix each failure, then run that check again.

Done when: the four checks pass, and the report to the user gives the slide
budget, the slide count, the assumptions, and the open findings.
