"""Deterministic, exhaustive UI test shards on separate disposable CI runners."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

SUITE = "tests/test_pr4_acceptance.py"
SHARDS = ("soak-chromium", "soak-webkit", "ui-0", "ui-1", "ui-2", "ui-3")
SOAK = "test_performance_soak_real_polling_session_and_retention"


def partition(nodes):
    if not nodes or len(nodes) != len(set(nodes)):
        raise ValueError("Empty or duplicate collection")
    groups = {shard: [] for shard in SHARDS}
    ordinary = []
    for node in nodes:
        name = node.split("::", 1)[1]
        if name == SOAK + "[chromium]":
            groups["soak-chromium"].append(node)
        elif name == SOAK + "[webkit]":
            groups["soak-webkit"].append(node)
        else:
            ordinary.append(node)
    if any(len(groups[s]) != 1 for s in SHARDS[:2]):
        raise ValueError("Real-time soak must run once per browser")
    for i, node in enumerate(ordinary):
        groups[SHARDS[2 + i % 4]].append(node)
    if any(not group for group in groups.values()):
        raise ValueError("Empty shard")
    return groups


def run(shard):
    out = Path("artifacts/ci-timing")
    out.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, "-m", "pytest"]
    result = subprocess.run(
        args + ["--collect-only", "-q", SUITE, "-m", "browser"],
        check=True, text=True, stdout=subprocess.PIPE,
    )
    nodes = [line.strip() for line in result.stdout.splitlines()
             if line.startswith(SUITE + "::")]
    selected = partition(nodes)[shard]
    (out / "manifest.json").write_text(json.dumps(
        {"shard": shard, "collected": nodes, "selected": selected}, indent=2))
    return subprocess.call(args + ["-vv", "-s", "--durations=0",
        "--durations-min=0", "--junitxml=" + str(out / "junit.xml")] + selected)


def verify(root, target):
    inventory = None
    seen = set()
    count = 0
    for shard in SHARDS:
        source = root / ("ci-ui-shard-" + shard)
        timing = source / "ci-timing"
        manifest = json.loads((timing / "manifest.json").read_text())
        nodes = manifest["collected"]
        if inventory is None:
            inventory = nodes
        if nodes != inventory or manifest["shard"] != shard:
            raise ValueError("Inconsistent collection: " + shard)
        selected = partition(nodes)[shard]
        if selected != manifest["selected"] or seen.intersection(selected):
            raise ValueError("Missing or overlapping selection: " + shard)
        cases = ET.parse(timing / "junit.xml").findall(".//testcase")
        expected = sorted(n.split("::", 1)[1] for n in selected)
        if sorted(c.attrib["name"] for c in cases) != expected:
            raise ValueError("JUnit execution differs from collection: " + shard)
        if any(c.find(tag) is not None for c in cases
               for tag in ("failure", "error", "skipped")):
            raise ValueError("Non-passing UI test: " + shard)
        seen.update(selected)
        count += len(cases)
        for path in (source / "pr4-ui").rglob("*"):
            if path.is_file():
                dest = target / path.relative_to(source / "pr4-ui")
                if dest.exists():
                    raise ValueError("Duplicate UI artifact: " + str(dest))
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
        print(f"{shard}: {len(cases)} tests, "
              f"{sum(float(c.attrib['time']) for c in cases):.2f}s")
    if seen != set(inventory or []):
        raise ValueError("Full UI coverage not preserved")
    print(f"Verified {count} distinct passing UI tests across {len(SHARDS)} isolated runners")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    runner = sub.add_parser("run")
    runner.add_argument("shard", choices=SHARDS)
    verifier = sub.add_parser("verify")
    verifier.add_argument("root", type=Path)
    verifier.add_argument("target", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        return run(args.shard)
    verify(args.root, args.target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
