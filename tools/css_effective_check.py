#!/usr/bin/env python3
"""Compare final CSS declarations against the reviewed pre-refactor cascade.

This detects accidental changes to declaration winners without storing a second
copy of the stylesheet. A matching hash is not a substitute for browser tests:
specificity interactions and runtime CSS state still need visual regression.

--write is intentionally a manual operation; never run it in CI.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import argparse
import json
import subprocess
import tinycss2

ROOT=Path(__file__).resolve().parents[1]
CSS=ROOT/"public"/"styles.css"
BASELINE=ROOT/"tests"/"baselines"/"ui-css-effective.sha256"


def fingerprint(source: str) -> tuple[str,int]:
    values={}
    def visit(nodes, context="base"):
        for r in nodes:
            if r.type=="qualified-rule":
                selector=tinycss2.serialize(r.prelude).strip()
                for d in tinycss2.parse_declaration_list(r.content,skip_comments=True,skip_whitespace=True):
                    if d.type=="error":
                        raise ValueError(f"CSS parse error for {selector}: {d.message}")
                    if d.type!="declaration":
                        continue
                    key=(context,selector,d.lower_name)
                    old=values.get(key)
                    important=bool(d.important)
                    # Important wins over normal; on equal importance, later wins.
                    if old is None or important>=old["important"]:
                        values[key]={"value":tinycss2.serialize(d.value).strip(),
                                     "important":important}
            elif r.type=="at-rule" and r.content is not None and r.lower_at_keyword in (
                "media","supports","container","layer","keyframes"
            ):
                query=tinycss2.serialize(r.prelude).strip()
                visit(tinycss2.parse_rule_list(r.content,skip_comments=True,skip_whitespace=True),
                      f"{context} > @{r.lower_at_keyword} {query}")
            elif r.type=="error":
                raise ValueError(f"CSS parse error: {r.message}")
    visit(tinycss2.parse_stylesheet(source,skip_comments=True,skip_whitespace=True))
    stable=[(*key,value["value"],value["important"]) for key,value in values.items()]
    stable.sort()
    encoded=json.dumps(stable,ensure_ascii=False,separators=(",",":")).encode()
    return sha256(encoded).hexdigest(),len(stable)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--check",action="store_true")
    parser.add_argument("--write",action="store_true")
    parser.add_argument("--baseline-head",action="store_true",help="Use git HEAD CSS to set the pre-change reference")
    args=parser.parse_args()
    if sum([args.check,args.write,args.baseline_head])!=1:
        parser.error("Choose exactly one of --check, --write, --baseline-head")
    if args.baseline_head:
        source=subprocess.check_output(["git","show","HEAD:public/styles.css"],cwd=ROOT).decode("utf8")
    else:
        source=CSS.read_text(encoding="utf8")
    digest,count=fingerprint(source)
    if args.check:
        expected=BASELINE.read_text().strip()
        if expected!=digest:
            raise SystemExit(f"CSS effective declaration baseline changed: expected {expected}, got {digest}")
        print(f"CSS cascade winners preserved: {count} declaration keys, SHA256 {digest[:12]}")
    else:
        BASELINE.parent.mkdir(parents=True,exist_ok=True)
        BASELINE.write_text(digest+"\n")
        print(f"Stored CSS effective baseline: {count} declaration keys, SHA256 {digest}")


if __name__=="__main__":
    main()
