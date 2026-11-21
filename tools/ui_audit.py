#!/usr/bin/env python3
"""Deterministic source inventory of CSS overrides; development only.

Usage:
  pip install -r tools/requirements-ui.txt
  python tools/ui_audit.py
  python tools/ui_audit.py --check
"""
from collections import Counter, defaultdict
from pathlib import Path
import argparse
import difflib
import tinycss2

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "public" / "styles.css"
TARGET = ROOT / "docs" / "UI_RULE_REGISTRY.md"


def rules_from(source: str):
    rules = []
    def visit(nodes, context="base"):
        for item in nodes:
            if item.type == "qualified-rule":
                selector = tinycss2.serialize(item.prelude).strip()
                declarations = tinycss2.parse_declaration_list(
                    item.content, skip_comments=True, skip_whitespace=True
                )
                for d in declarations:
                    if d.type == "declaration":
                        rules.append({
                            "context": context,
                            "selector": selector,
                            "property": d.lower_name,
                            "value": tinycss2.serialize(d.value).strip(),
                            "line": item.source_line,
                        })
            elif item.type == "at-rule" and item.content is not None and item.lower_at_keyword in (
                "media", "supports", "container", "layer"
            ):
                query = tinycss2.serialize(item.prelude).strip()
                visit(tinycss2.parse_rule_list(
                    item.content, skip_comments=True, skip_whitespace=True
                ), context + " > @" + item.lower_at_keyword + " " + query)
    visit(tinycss2.parse_stylesheet(source, skip_comments=True, skip_whitespace=True))
    return rules


def esc(text: str, limit=100):
    value = str(text).replace("|", "\\|").replace("\n", " ")
    trimmed = value[:limit-1]+"…" if len(value)>limit else value
    return chr(96)+trimmed+chr(96)


def report(source: str):
    rules = rules_from(source)
    blocks = defaultdict(list)
    properties = defaultdict(list)
    for r in rules:
        key = (r["context"], r["selector"], r["line"])
        if key not in blocks[r["selector"]]:
            blocks[r["selector"]].append(key)
        properties[(r["context"],r["selector"],r["property"])].append(r)
    repeated = [(selector, occurrences) for selector,occurrences in blocks.items()
                if len(occurrences)>1]
    repeated.sort(key=lambda v:(-len(v[1]),v[0]))
    conflicting = [recs for recs in properties.values()
                   if len({r["value"] for r in recs})>1]
    conflicting.sort(key=lambda recs:(recs[0]["selector"],
                                      recs[0]["context"],recs[0]["property"]))
    all_blocks = set((r["context"],r["selector"],r["line"]) for r in rules)
    contexts=Counter(r["context"] for r in rules)
    out=[
        "# UI CSS rule registry (generated)",
        "",
        "Source of truth: " + esc("public/styles.css") + " at the current checkout. Regenerate:",
        esc("python tools/ui_audit.py") + " (" + esc("--check") + " in CI).",
        "",
        "A repeat is not automatically a defect: responsive and state-specific overrides are expected.",
        "A **conflict** here means the same selector, CSS property and at-rule context",
        "have different declarations in source order. The last declaration is not",
        "necessarily the winner if specificity, importance or cascading conditions differ.",
        "",
        f"- Qualified rule blocks: **{len(all_blocks)}**",
        f"- Unique selectors: **{len(blocks)}**",
        f"- Selectors in multiple blocks: **{len(repeated)}**",
        f"- Differing declarations in the same context: **{len(conflicting)}**",
        f"- At-rule contexts: **{len(contexts)}**",
        "",
        "## Same-context differing declarations",
        "",
        "| Selector | Context | Property | Earlier → later | Source lines |",
        "|---|---|---|---|---|",
    ]
    for recs in conflicting:
        dedup=list(dict.fromkeys(r["value"] for r in recs))
        out.append("| "+ " | ".join([
            esc(recs[0]["selector"],75),esc(recs[0]["context"],45),
            esc(recs[0]["property"],35),
            " → ".join(esc(v,60) for v in dedup),
            ", ".join(str(r["line"]) for r in recs)
        ])+" |")
    out.extend(["","## Selectors declared in multiple blocks","","| Selector | Blocks | Contexts / source lines |",
                "|---|---:|---|"])
    for selector, occurrences in repeated:
        contexts_text=", ".join(f"{ctx}@{line}" for ctx,sel,line in occurrences)
        out.append(f"| {esc(selector,100)} | {len(occurrences)} | {esc(contexts_text,230)} |")
    out.extend(["","## Context inventory","","| Context | Declaration count |","|---|---:|"])
    for ctx,num in contexts.most_common():out.append(f"| {esc(ctx)} | {num} |")
    out.append("")
    return "\n".join(out)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--check",action="store_true")
    args=parser.parse_args()
    expected=report(SOURCE.read_text(encoding="utf8"))
    if args.check:
        actual=TARGET.read_text(encoding="utf8") if TARGET.exists() else ""
        if actual!=expected:
            print("UI rule registry is stale. Regenerate with python tools/ui_audit.py")
            print("".join(difflib.unified_diff(actual.splitlines(True),expected.splitlines(True),n=2))[:4000])
            raise SystemExit(1)
        print("UI registry current")
    else:
        TARGET.parent.mkdir(parents=True,exist_ok=True)
        TARGET.write_text(expected,encoding="utf8")
        print(f"Wrote {TARGET.relative_to(ROOT)}")


if __name__=="__main__":
    main()
