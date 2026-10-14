#!/usr/bin/env python3
"""Classify one non-interactive Claude critic call for the pressure-test skill.

Usage: critic_status.py EVENTS REPLY ALLOWED_MODEL...

EVENTS is the stdout of `claude -p --output-format stream-json --verbose`.
The script writes the critic's final reply to REPLY and prints one status:

  ok                 an allowed model answered
  refused            Claude flagged the request; retry on the fallback model
  wrong_model:IDS    a message came from a model outside ALLOWED_MODEL
  error:DETAIL       the call failed or produced no final result
"""

from __future__ import annotations

import json
import sys

REFUSAL_EVENTS = {"model_refusal_fallback", "model_refusal_no_fallback"}


def read_events(path: str) -> list[dict]:
    """Return the JSON objects in a stream-json file; skip other lines."""
    events = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return events


def is_refused(events: list[dict], result: dict | None) -> bool:
    """Return True when Claude flagged this call and the fallback model must retry it.

    Any safety stop counts, even when the answer completed:
    - an assistant event whose message has stop_reason "refusal"
    - the result event's stop_reason "refusal", or safety_stops above zero
    - a system event with subtype "model_refusal_fallback" or
      "model_refusal_no_fallback"
    """
    if result and (result.get("stop_reason") == "refusal" or (result.get("safety_stops") or 0) > 0):
        return True
    for event in events:
        kind = event.get("type")
        if kind == "assistant" and (event.get("message") or {}).get("stop_reason") == "refusal":
            return True
        if kind == "system" and event.get("subtype") in REFUSAL_EVENTS:
            return True
    return False


def answer_models(events: list[dict]) -> set[str]:
    """Return the models that wrote assistant messages.

    Claude Code labels its own error text with a model such as "<synthetic>";
    those messages are not model output.
    """
    models = set()
    for event in events:
        if event.get("type") != "assistant":
            continue
        model = (event.get("message") or {}).get("model")
        if model and not model.startswith("<"):
            models.add(model)
    return models


def classify(events: list[dict], allowed: list[str]) -> tuple[str, str]:
    """Return the status line and the critic's final reply."""
    result = next((e for e in reversed(events) if e.get("type") == "result"), None)
    reply = (result or {}).get("result") or ""
    if is_refused(events, result):
        return "refused", reply
    unexpected = sorted(answer_models(events) - set(allowed))
    if unexpected:
        return "wrong_model:" + ",".join(unexpected), reply
    if result is None:
        return "error:no result event", reply
    if result.get("is_error") or result.get("subtype") != "success":
        return f"error:{result.get('subtype') or 'is_error'}", reply
    return "ok", reply


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    events_path, reply_path, *allowed = argv[1:]
    try:
        events = read_events(events_path)
    except OSError as error:
        status, reply = f"error:cannot read events ({error.strerror})", ""
    else:
        status, reply = classify(events, allowed)
    with open(reply_path, "w", encoding="utf-8") as handle:
        handle.write(reply)
    print(status)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
