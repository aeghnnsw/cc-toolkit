---
name: sci-slides
description: Use when creating, revising, or reviewing slides for an academic or STEM talk (conference talk, lab meeting, thesis defence, or journal club), including the talk's story and length, slide titles, claims about data, reused figures, and slide design.
---

# Scientific Presentation Slides

Build each slide as an assertion and its evidence: a one-line title states the
finding, and the slide shows the data behind it. The audience hears the speaker
and sees only the screen, so every word on a slide must decode from what is on
screen and what the audience already knows.

## Rule sources

Apply the rules in this order. An earlier source wins a conflict.

1. The user's request in this conversation.
2. The standing rules in the project's `slide-rules.md`.
3. The template the user supplies: layouts, footer, logo, fonts, and colours.
4. This skill's references: [slide text](references/slide-text.md) and
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

Ask for every missing item in one message. When no `slide-rules.md` exists,
add one question to that message: which standing rules apply to all of this
presenter's decks (template, wording to avoid, label and number conventions,
notes style). Save the answers to `slide-rules.md` at the project root under
the headings Template, Wording, Labels, and Notes. Keep presenter-specific
rules in that file only. When the user cannot answer, record an assumption for
each missing item and report it.

Done when: each brief item has a value or a recorded assumption, and the
standing rules are loaded or saved.

### 2. Plan the story and the slide budget

Set the slide budget to about one content slide per speaking minute. Speaking
time is the slot minus Q&A; when the Q&A time is unknown, assume 20% of the
slot. Title and backup slides do not count against the budget.

Write the slide list:

- Open the talk with the question the speaker asks, and each section with its
  own question.
- Give each slide a draft assertion title.
- End each section with a transition that raises the next question and holds
  no answer.
- Move detail beyond the budget to the notes or to backup slides after the
  last slide.

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

1. **Meaning.** For each title and sentence, name the number or figure that
   supports it. State what that quantity measures: what, compared with what,
   in which population, at which threshold. Check that the sentence claims
   that and no more, and that the title claims only what the slide shows.
   Check each number against its source.
2. **Definitions.** List each term, abbreviation, dataset name, and figure
   marker. Check that each is defined where it first appears.
3. **Figures.** Check that each reused figure shows its source, its reason, and
   the meaning of its markers. Check that each schematic is labelled and
   carries no invented numbers.
4. **Wording.** Check that each word decodes from the screen and the
   audience's knowledge, and that each item is named by its content.
5. **Form.** Check the title, text, and design rules, the template, and each
   standing rule.

Fix each finding, then run the passes again on the slides that you changed.
Report a finding that needs the user's input, such as a missing source or an
unknown threshold, instead of guessing.

Done when: each slide in the section passes all five passes, or its open
findings are in the report for the user.

Repeat steps 3 and 4 until every section is drafted and reviewed.

### 5. Review the deck

- **Story:** the talk and each section open with their questions, each
  transition raises the next question, and each message has its evidence.
- **Budget:** the content slide count is within the slide budget.
- **Terms:** each concept has one term across all sections, defined at its
  first use.
- **Layout:** when a renderer is available, render the deck and inspect each
  slide: each title fits one line, no text overflows, and each label is
  readable. Otherwise, report that the layout was not checked.

Done when: the four checks pass, and the report to the user gives the slide
budget, the slide count, the assumptions, and the open findings.
