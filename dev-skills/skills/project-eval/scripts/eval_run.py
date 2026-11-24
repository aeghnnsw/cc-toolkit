#!/usr/bin/env python3
"""Check the run results and the report of a project-eval run.

Usage, from the project root:

    python3 <skill-dir>/scripts/eval_run.py check <RUN>
    python3 <skill-dir>/scripts/eval_run.py path <slug>
    python3 <skill-dir>/scripts/eval_run.py lint <report> [--custom-path]

check reads the evaluator results <RUN>/E<N>.md and the verifier results
<RUN>/V-*.md. It prints one line for each evaluator, with its finding count
and stop reason, and a PROBLEM line for each of these:

- A finding heading in E<N>.md with no ID, a duplicate ID, or an ID that is
  not "E<N>-<k>. ". The line names a free ID to use. A finding heading is a
  heading outside a code block that starts with an ID, such as "E2-3", or
  ends with a severity in parentheses.
- An evaluator result with no "Stop reason" line, or with a stop reason
  that is not "deadline", "two angles with nothing new", or
  "partial: <reason>". The last "Stop reason" line of a file counts.
- A verdict line with fewer than four fields, a verdict for an ID that no
  E<N>.md has, a verdict that is not Confirmed, Plausible, or Rejected, a
  Confirmed or Plausible verdict whose severity does not start with
  Critical, Major, or Minor, or a second verdict for an ID that differs from
  the first. The later verdict counts. A verdict line is a line whose first
  "|"-separated field is an ID.

A finding with no verdict, or with only bad verdict lines, has no verdict.
check then prints the "No verdict" IDs, the Summary of report-format.md
counted by finding ID, and the Status line of the report. An evaluator with
no valid stop reason counts as partial.

path prints the default report path for the slug: docs/eval/ in the current
folder, the current local time, and a -N suffix when the name is taken. It
also prints the earlier reports with the same slug. A slug is lowercase
words joined by hyphens, and it does not end in a number.

lint checks a report in the format of report-format.md: the default name
(skip this with --custom-path), the title, the header fields, the sections
and their order, the Summary rows, and the counts of the Summary against
the finding headings and the tables. The Earlier reports field names each
report in the same folder that has the same slug and an earlier name, or
says "none". The Run results field names a folder that exists.

Exit status: 0 when the command prints no PROBLEM line; 1 when it prints
one; 2 for a usage error, such as a run folder with no E<N>.md file.
Python 3.9 or newer, standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

SEVERITIES = ("Critical", "Major", "Minor")
VERDICTS = ("Confirmed", "Plausible", "Rejected")
STOP_REASONS = ("deadline", "two angles with nothing new")
HEADER_FIELDS = ("Date", "Scope", "Criteria", "App", "Evaluators", "Status", "Browser checks",
                 "Earlier reports", "Run results")
SECTIONS = ("Summary", "Findings", "Rejected Findings", "Not Verified Findings", "Coverage")
COVERAGE_FIELDS = ("Not covered", "Other areas")
REPORT_DIR = Path("docs", "eval")

HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
EVALUATOR_FILE = re.compile(r"^E([1-9]\d*)\.md$")
FINDING_ID = re.compile(r"^(E([1-9]\d*)-([1-9]\d*))\.\s+\S")
ID_START = re.compile(r"^E\d", re.IGNORECASE)
SEVERITY_END = re.compile(r"\((?:Critical|Major|Minor)\b[^)]*\)$", re.IGNORECASE)
VERDICT_ID = re.compile(r"^E[1-9]\d*-[1-9]\d*$")
SEVERITY_WORD = re.compile(r"[*_`\s]*([A-Za-z]+)")
LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
STOP_LINE = re.compile(r"^[\s>#*\-\d.]*stop reason[*_]*\s*(?::\s*(.*))?$", re.IGNORECASE)
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
REPORT_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2}-\d{4})-([a-z0-9]+(?:-[a-z0-9]+)*)\.md$")
REPORT_FILE = re.compile(r"\d{4}-\d{2}-\d{2}-\d{4}-[a-z0-9-]+\.md")
TITLE = re.compile(r"^# Project Evaluation: \S")
FIELD = re.compile(r"^- \*\*(.+?)\*\*:\s*(.*)$")
DATE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \S")
STATUS = re.compile(r"^(?:Complete|Incomplete \(.+\))$")
BROWSER = re.compile(r"^(?:done|not needed|skipped: .+)$")
REPORT_FINDING = re.compile(r"^F[1-9]\d*\. .+ \((Critical|Major|Minor), (Confirmed|Plausible)\)$")
COUNTS = re.compile(r"^Rejected: (\d+)\. Not verified: (\d+)\.$")
SEPARATOR = re.compile(r"^\|[\s:|-]+\|$")
EMPHASIS = "*_` \"'"


def fail(message: str) -> None:
    print(f"eval_run.py: {message}", file=sys.stderr)
    sys.exit(2)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def prose_lines(text: str):
    """Yield the number and text of each line outside fenced code blocks."""
    fence = ""
    for number, line in enumerate(text.splitlines(), 1):
        match = FENCE.match(line)
        if fence:
            mark = line.strip()
            if match and set(mark) == {fence[0]} and len(mark) >= len(fence):
                fence = ""
        elif match:
            fence = match.group(1)
        else:
            yield number, line


def clean(value: str) -> str:
    """Return a value without emphasis, quotes, or a final period around it."""
    return value.strip().strip(EMPHASIS).rstrip(".").strip(EMPHASIS)


def canonical(value: str, names: tuple[str, ...]) -> str | None:
    """Return the name that the value spells, without regard to case, or None."""
    return next((name for name in names if name.lower() == clean(value).lower()), None)


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


# check


def finding_headings(text: str):
    """Yield the line number and text of each finding heading."""
    for number, line in prose_lines(text):
        match = HEADING.match(line)
        if match and len(match.group(1)) > 1:
            title = match.group(2).strip("*_ ")
            if ID_START.match(title) or SEVERITY_END.search(title):
                yield number, title


def stop_reason(text: str) -> tuple[int, str] | None:
    """Return the line number and value of the last stop reason, or None.

    The value follows "Stop reason:" on its line, or is the next nonblank line
    after a "Stop reason" label or heading.
    """
    found, label = None, False
    for number, line in prose_lines(text):
        if label and line.strip():
            found, label = (number, clean(line)), False
            continue
        match = STOP_LINE.match(line)
        if match:
            value = clean(match.group(1) or "")
            found, label = ((number, value), False) if value else (found, True)
    return found


def check_evaluator(n: int, path: Path, problems: list[str]) -> tuple[list[str], str, bool]:
    """Return the finding IDs, the stop reason, and whether the evaluator is partial."""
    text = read(path)
    ids: dict[str, int] = {}
    bad = []
    for number, title in finding_headings(text):
        match = FINDING_ID.match(title)
        if match and int(match.group(2)) == n:
            if match.group(1) in ids:
                bad.append((number, f"duplicate ID {match.group(1)} (first at line {ids[match.group(1)]})"))
            else:
                ids[match.group(1)] = number
        elif ID_START.match(title):
            word = title.split()[0].rstrip(".:")
            bad.append((number, f'malformed ID "{word}": write "E{n}-<k>. <Title> (<Severity>)"'))
        else:
            bad.append((number, "finding has no ID"))
    free = max((int(i.split("-")[1]) for i in ids), default=0) + 1
    for number, problem in bad:
        problems.append(f"{path.name}:{number}: {problem}; use the free ID E{n}-{free}")
        free += 1
    stop = stop_reason(text)
    if stop is None:
        problems.append(f'{path.name}: no stop reason; append the line "**Stop reason**: partial: <reason>"')
        return list(ids), "none", True
    number, reason = stop
    if reason.lower() in STOP_REASONS:
        return list(ids), reason, False
    if not reason.lower().startswith("partial"):
        problems.append(f'{path.name}:{number}: unknown stop reason "{reason}"; use deadline, '
                        "two angles with nothing new, or partial: <reason>")
    return list(ids), reason, True


def read_verdicts(run: Path, known: set[str], problems: list[str]) -> dict[str, tuple[str, str]]:
    """Return {ID: (verdict, severity)} from the verifier results; Rejected has no severity."""
    verdicts: dict[str, tuple[tuple[str, str], str]] = {}
    for path in sorted(run.glob("V-*.md")):
        # A verifier can put its verdict lines in a code block, so no line is skipped.
        for number, line in enumerate(read(path).splitlines(), 1):
            fields = table_cells(LIST_MARKER.sub("", line))
            finding = clean(fields[0]).rstrip(".:")
            if not VERDICT_ID.match(finding):
                continue
            where = f"{path.name}:{number}"
            if len(fields) < 4:
                problems.append(f'{where}: malformed verdict line; write "<ID> | <Verdict> | <Severity> | <Reason>"')
                continue
            if finding not in known:
                problems.append(f"{where}: verdict for {finding}, which no E<N>.md has")
                continue
            verdict = canonical(fields[1], VERDICTS)
            if verdict is None:
                problems.append(f'{where}: bad verdict "{fields[1]}" for {finding}; use Confirmed, Plausible, '
                                "or Rejected")
                continue
            severity = ""
            if verdict != "Rejected":
                word = SEVERITY_WORD.match(fields[2])
                severity = canonical(word.group(1), SEVERITIES) if word else None
                if not severity:
                    problems.append(f'{where}: bad severity "{fields[2]}" for {finding}; start it with Critical, '
                                    "Major, or Minor")
                    continue
            entry = (verdict, severity)
            if finding in verdicts and verdicts[finding][0] != entry:
                first, at = verdicts[finding]
                problems.append(f"{where}: {finding} has a second verdict, {' '.join(entry).strip()}, which "
                                f"differs from {' '.join(first).strip()} at {at}")
            verdicts[finding] = (entry, where)
    return {finding: entry for finding, (entry, _) in verdicts.items()}


def summary(confirmed: Counter, plausible: Counter, rejected: int, unverified: int) -> list[str]:
    rows = [f"| {severity} | {confirmed[severity]} | {plausible[severity]} |" for severity in SEVERITIES]
    return ["| Severity | Confirmed | Plausible |", "|----------|-----------|-----------|", *rows, "",
            f"Rejected: {rejected}. Not verified: {unverified}."]


def status(unverified: int, partial: list[int]) -> str:
    causes = []
    if unverified:
        causes.append(f"{unverified} finding{'s' if unverified > 1 else ''} not verified")
    if partial:
        causes.append(", ".join(f"E{n}" for n in partial) + " partial")
    return f"Incomplete ({'; '.join(causes)})" if causes else "Complete"


def check(run: Path) -> int:
    if not run.is_dir():
        fail(f"{run} is not a folder")
    evaluators = sorted((int(match.group(1)), path) for path in run.iterdir()
                        if (match := EVALUATOR_FILE.match(path.name)))
    if not evaluators:
        fail(f"{run} has no E<N>.md file")
    problems: list[str] = []
    known: list[str] = []
    partial: list[int] = []
    lines = []
    for n, path in evaluators:
        ids, reason, is_partial = check_evaluator(n, path, problems)
        known += ids
        if is_partial:
            partial.append(n)
        lines.append(f"{path.name}: {len(ids)} finding{'' if len(ids) == 1 else 's'}; stop reason: {reason}")
    verdicts = read_verdicts(run, set(known), problems)
    missing = [finding for finding in known if finding not in verdicts]
    confirmed = Counter(s for v, s in verdicts.values() if v == "Confirmed")
    plausible = Counter(s for v, s in verdicts.values() if v == "Plausible")
    rejected = sum(v == "Rejected" for v, _ in verdicts.values())
    print("\n".join(lines))
    for problem in problems:
        print(f"PROBLEM {problem}")
    print(f"No verdict: {', '.join(missing) or 'none'}")
    print("\nSummary by finding ID, before you merge duplicates:\n")
    print("\n".join(summary(confirmed, plausible, rejected, len(missing))))
    print(f"\nStatus: {status(len(missing), partial)}")
    return 1 if problems else 0


# path and lint


def parse_name(name: str) -> tuple[str, str, int] | None:
    """Return the time stamp, the slug, and the -N suffix (1 for none) of a report name, or None."""
    match = REPORT_NAME.match(name)
    if not match:
        return None
    stamp, slug = match.groups()
    head, _, last = slug.rpartition("-")
    return (stamp, head, int(last)) if head and last.isdigit() else (stamp, slug, 1)


def same_slug(folder: Path, slug: str) -> list[str]:
    """Return the report names in the folder that have the slug, oldest first."""
    names = [path.name for path in folder.glob("*.md")] if folder.is_dir() else []
    parsed = [(parse_name(name), name) for name in names]
    return [name for key, name in sorted((key, name) for key, name in parsed if key and key[1] == slug)]


def default_path(folder: Path, slug: str, now: datetime) -> Path:
    """Return the first free default report path for the slug at the time."""
    stamp, n = now.strftime("%Y-%m-%d-%H%M"), 1
    path = folder / f"{stamp}-{slug}.md"
    while path.exists():
        n += 1
        path = folder / f"{stamp}-{slug}-{n}.md"
    return path


def path_command(slug: str) -> int:
    if not SLUG.fullmatch(slug):
        fail(f'the slug "{slug}" is not lowercase words joined by hyphens')
    if slug.rpartition("-")[2].isdigit():
        fail(f'the slug "{slug}" ends in a number, which reads as the -N suffix')
    earlier = [str(REPORT_DIR / name) for name in same_slug(REPORT_DIR, slug)]
    print(f"Report path: {default_path(REPORT_DIR, slug, datetime.now())}")
    print(f"Earlier reports: {', '.join(earlier) or 'none'}")
    return 0


def table_rows(lines: list[tuple[int, str]]) -> int:
    """Return the number of body rows of the first table in the lines."""
    rows = [line.strip() for _, line in lines if line.strip().startswith("|")]
    if len(rows) > 1 and SEPARATOR.match(rows[1]):
        return len(rows) - 2
    return max(len(rows) - 1, 0)


def lint_name(report: Path, problems: list[str]) -> None:
    if report.resolve().parent.parts[-2:] != REPORT_DIR.parts:
        problems.append(f"{report}: the default path is in {REPORT_DIR}/; pass --custom-path for a path "
                        "that the user or a calling skill named")
    parsed = parse_name(report.name)
    if not parsed:
        problems.append(f"{report}: the name is not YYYY-MM-DD-HHMM-<slug>.md or YYYY-MM-DD-HHMM-<slug>-<N>.md")
        return
    stamp, _, n = parsed
    try:
        datetime.strptime(stamp, "%Y-%m-%d-%H%M")
    except ValueError:
        problems.append(f"{report}: {stamp} is not a valid date and time")
    if report.stem.rpartition("-")[2].isdigit() and n < 2:
        problems.append(f"{report}: the -N suffix starts at -2, and a slug does not end in a number")


def lint_header(report: Path, header: list[tuple[int, str]], problems: list[str]) -> dict[str, str]:
    fields: dict[str, tuple[int, str]] = {}
    for number, line in header:
        match = FIELD.match(line)
        if match and match.group(1) in HEADER_FIELDS:
            if match.group(1) in fields:
                problems.append(f"{report}:{number}: a second {match.group(1)} field")
            fields[match.group(1)] = (number, match.group(2).strip())
    for name in HEADER_FIELDS:
        if name not in fields:
            problems.append(f'{report}: no "- **{name}**:" header field')
        elif not fields[name][1]:
            problems.append(f"{report}:{fields[name][0]}: the {name} field is empty")
    values = {name: value for name, (_, value) in fields.items() if value}
    checks = (("Date", DATE, "<YYYY-MM-DD HH:MM time zone>"),
              ("Status", STATUS, "Complete | Incomplete (<causes>)"),
              ("Browser checks", BROWSER, "done | not needed | skipped: <reason>"))
    for name, pattern, form in checks:
        if name in values and not pattern.match(values[name]):
            problems.append(f'{report}:{fields[name][0]}: the {name} field is not "{form}"')
    if "Date" in values and DATE.match(values["Date"]):
        try:
            datetime.strptime(DATE.match(values["Date"]).group(1), "%Y-%m-%d %H:%M")
        except ValueError:
            problems.append(f"{report}:{fields['Date'][0]}: the Date field is not a valid date and time")
    if "Run results" in values and not Path(clean(values["Run results"])).is_dir():
        problems.append(f"{report}:{fields['Run results'][0]}: the Run results field does not name a folder "
                        "that exists")
    parsed = parse_name(report.name)
    if "Earlier reports" in values and parsed:
        number = fields["Earlier reports"][0]
        key = (parsed[0], parsed[2])
        expected = [name for name in same_slug(report.parent, parsed[1])
                    if (parse_name(name)[0], parse_name(name)[2]) < key]
        named = set(REPORT_FILE.findall(values["Earlier reports"]))
        if not expected and clean(values["Earlier reports"]).lower() != "none":
            problems.append(f'{report}:{number}: no earlier report has the slug {parsed[1]}; write "none"')
        for name in expected:
            if name not in named:
                problems.append(f"{report}:{number}: Earlier reports does not name {name}")
        for name in sorted(named - set(expected)):
            problems.append(f"{report}:{number}: Earlier reports names {name}, which is not an earlier report "
                            f"with the slug {parsed[1]} in {report.parent}")
    return values


def lint(report: Path, custom_path: bool) -> int:
    if not report.is_file():
        fail(f"{report} is not a file")
    problems: list[str] = []
    if not custom_path:
        lint_name(report, problems)
    lines = list(prose_lines(read(report)))
    if not next((TITLE.match(line) for _, line in lines if line.strip()), None):
        problems.append(f'{report}: the first line is not "# Project Evaluation: <target>"')
    header: list[tuple[int, str]] = []
    sections: dict[str, list[tuple[int, str]]] = {}
    order: list[str] = []
    body = header
    for number, line in lines:
        match = HEADING.match(line)
        if match and len(match.group(1)) == 2:
            name = match.group(2)
            if name in sections:
                problems.append(f'{report}:{number}: a second "## {name}" section')
                body = sections[name]
            else:
                order.append(name)
                body = sections[name] = []
        else:
            body.append((number, line))
    lint_header(report, header, problems)

    for name in SECTIONS:
        if name not in sections and name != "Not Verified Findings":
            problems.append(f'{report}: no "## {name}" section')
    known = [name for name in order if name in SECTIONS]
    if known != [name for name in SECTIONS if name in known]:
        problems.append(f"{report}: the sections are not in the order {', '.join(SECTIONS)}")

    table: dict[str, tuple[int, int]] = {}
    counts = None
    for number, line in sections.get("Summary", []):
        cells = table_cells(line)
        if line.strip().startswith("|") and cells[0] in SEVERITIES:
            if len(cells) == 3 and cells[1].isdigit() and cells[2].isdigit():
                table[cells[0]] = (int(cells[1]), int(cells[2]))
            else:
                problems.append(f'{report}:{number}: the Summary row is not "| {cells[0]} | <n> | <n> |"')
        counts = counts or COUNTS.match(line.strip())
    if "Summary" in sections:
        for severity in SEVERITIES:
            if severity not in table:
                problems.append(f'{report}: the Summary has no "| {severity} | <n> | <n> |" row')
        if not counts:
            problems.append(f'{report}: the Summary has no "Rejected: <n>. Not verified: <n>." line')

    found: Counter = Counter()
    for number, line in sections.get("Findings", []):
        match = HEADING.match(line)
        if match and len(match.group(1)) == 3:
            finding = REPORT_FINDING.match(match.group(2))
            if finding:
                found[finding.groups()] += 1
            else:
                problems.append(f'{report}:{number}: the finding heading is not "### F<k>. <Title> '
                                '(<Severity>, <Confirmed or Plausible>)"')
    for severity, (confirmed, plausible) in table.items():
        for verdict, count in (("Confirmed", confirmed), ("Plausible", plausible)):
            if count != found[severity, verdict]:
                problems.append(f"{report}: the Summary counts {count} {severity} {verdict}, and the Findings "
                                f"section has {found[severity, verdict]}")
    if counts:
        rejected, unverified = (int(group) for group in counts.groups())
        rows = table_rows(sections.get("Rejected Findings", []))
        if "Rejected Findings" in sections and rows != rejected:
            problems.append(f"{report}: the Summary counts {rejected} Rejected, and the Rejected Findings table "
                            f"has {rows} rows")
        if unverified and "Not Verified Findings" not in sections:
            problems.append(f'{report}: the Summary counts {unverified} Not verified, and there is no '
                            '"## Not Verified Findings" section')
        elif not unverified and "Not Verified Findings" in sections:
            problems.append(f"{report}: every finding has a verdict, so omit the Not Verified Findings section")
        elif unverified and table_rows(sections["Not Verified Findings"]) != unverified:
            problems.append(f"{report}: the Summary counts {unverified} Not verified, and the Not Verified "
                            f"Findings table has {table_rows(sections['Not Verified Findings'])} rows")

    coverage = {match.group(1) for _, line in sections.get("Coverage", []) if (match := FIELD.match(line))}
    for name in COVERAGE_FIELDS:
        if "Coverage" in sections and name not in coverage:
            problems.append(f'{report}: the Coverage section has no "- **{name}**:" line')

    for problem in problems:
        print(f"PROBLEM {problem}")
    print(f"{report}: {len(problems)} problem{'' if len(problems) == 1 else 's'}")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval_run.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="check the IDs, stop reasons, and verdicts of a run folder").add_argument(
        "run", type=Path, help="the run folder, <RUN>")
    sub.add_parser("path", help="print the default report path and the earlier reports").add_argument(
        "slug", help="lowercase words joined by hyphens, such as auth-module")
    lint_parser = sub.add_parser("lint", help="check a report against report-format.md")
    lint_parser.add_argument("report", type=Path, help="the report file")
    lint_parser.add_argument("--custom-path", action="store_true",
                             help="skip the default-name check, for a path that the user or a calling skill named")
    args = parser.parse_args(argv)
    if args.command == "check":
        return check(args.run)
    if args.command == "path":
        return path_command(args.slug)
    return lint(args.report, args.custom_path)


if __name__ == "__main__":
    sys.exit(main())
