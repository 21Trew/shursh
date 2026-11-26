"""Coverage gates must reject missing, repeated or non-passing browser cases."""
import json
from collections import Counter
import xml.etree.ElementTree as ET

import pytest

from tools.ci_ui_shards import SHARDS, SOAK, SUITE, partition, verify

NODES = [SUITE + "::" + SOAK + "[" + engine + "]"
         for engine in ("chromium", "webkit")]
NODES += [SUITE + "::test_case_" + str(i) for i in range(30)]
WEIGHTS = {node: i + 1 for i, node in enumerate(NODES)}


def test_partition_exact_inventory_and_stable_order():
    groups = partition(NODES, WEIGHTS)
    assert Counter(n for group in groups.values() for n in group) == Counter(NODES)
    assert groups["soak-chromium"] == NODES[:1]
    assert groups["soak-webkit"] == NODES[1:2]
    assert all(group == sorted(group, key=NODES.index) for group in groups.values())
    assert groups == partition(NODES, WEIGHTS)


def test_partition_balances_heavy_cases():
    weights = dict.fromkeys(NODES, 1.0)
    for node in NODES[2:2 + len(SHARDS[2:])]:
        weights[node] = 100.0
    groups = partition(NODES, weights)
    loads = [sum(weights[n] for n in groups[s]) for s in SHARDS[2:]]
    assert max(loads) - min(loads) <= 1


def test_partition_keeps_new_case_without_timing():
    added = SUITE + "::test_new"
    groups = partition(NODES + [added], WEIGHTS)
    assert sum(group.count(added) for group in groups.values()) == 1


@pytest.mark.parametrize("bad", [NODES[:1] + NODES[2:], NODES + NODES[2:3],
                                  NODES[:3], []])
def test_partition_rejects_invalid_collection(bad):
    with pytest.raises(ValueError):
        partition(bad, WEIGHTS)


@pytest.fixture
def artifacts(tmp_path):
    root, target = tmp_path / "input", tmp_path / "output"
    for shard, selected in partition(NODES, WEIGHTS).items():
        source = root / ("ci-ui-shard-" + shard)
        timing = source / "ci-timing"
        timing.mkdir(parents=True)
        (timing / "manifest.json").write_text(json.dumps(
            {"shard": shard, "collected": NODES, "selected": selected}))
        suite = ET.Element("testsuite")
        for node in selected:
            ET.SubElement(suite, "testcase", name=node.split("::", 1)[1], time="0.1")
        ET.ElementTree(suite).write(timing / "junit.xml")
        shots = source / "pr4-ui"
        shots.mkdir()
        (shots / (shard + ".png")).write_bytes(b"fixture")
    return root, target


def test_gate_restores_all_cases_and_artifacts(artifacts):
    root, target = artifacts
    assert verify(root, target, WEIGHTS) == len(NODES)
    assert len(list(target.glob("*.png"))) == len(SHARDS)


@pytest.mark.parametrize("defect", ["missing", "duplicate", "skipped", "failure",
                                    "inconsistent", "duplicate-artifact"])
def test_gate_rejects_invalid_artifacts(artifacts, defect):
    root, target = artifacts
    timing = root / "ci-ui-shard-ui-0" / "ci-timing"
    xml = timing / "junit.xml"
    tree = ET.parse(xml)
    suite = tree.getroot()
    if defect == "missing":
        suite.remove(suite[0])
    elif defect == "duplicate":
        suite.append(suite[0])
    elif defect in ("skipped", "failure"):
        ET.SubElement(suite[0], defect)
    elif defect == "inconsistent":
        manifest = timing / "manifest.json"
        data = json.loads(manifest.read_text())
        data["collected"].pop()
        manifest.write_text(json.dumps(data))
    elif defect == "duplicate-artifact":
        (root / "ci-ui-shard-ui-1" / "pr4-ui" / "ui-0.png").write_bytes(b"duplicate")
    tree.write(xml)
    with pytest.raises(ValueError):
        verify(root, target, WEIGHTS)
