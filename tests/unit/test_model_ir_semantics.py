"""Model IR: функциональное влияние входов на выход."""

import copy
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from simintech_api.model_ir import (  # noqa: E402
    SCHEMA,
    VERSION,
    BlockContractRegistry,
    ModelIndex,
    parse_xprt,
)
from simintech_api.model_ir.semantics import influence  # noqa: E402

MODEL = """<Header><project><page>
  <object><name>`K`</name><class_name>`Константа`</class_name>
    <obj_type>`100`</obj_type>
    <ports><port><name>`y`</name><mode>`1`</mode></port></ports>
  </object>
  <object><name>`G`</name><class_name>`Усилитель`</class_name>
    <obj_type>`100`</obj_type>
    <ports>
      <port><name>`u`</name><mode>`0`</mode></port>
      <port><name>`y`</name><mode>`1`</mode></port>
    </ports>
  </object>
  <object><name>`S`</name><class_name>`Временной график`</class_name>
    <obj_type>`106`</obj_type>
    <ports><port><name>`u`</name><mode>`0`</mode></port></ports>
  </object>
  <object><name>`W1`</name><class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`0`</start_bl_index><start_port_index>`0`</start_port_index>
    <end_bl_index>`1`</end_bl_index><end_port_index>`0`</end_port_index>
  </object>
  <object><name>`W2`</name><class_name>`Математическая связь`</class_name>
    <obj_type>`101`</obj_type>
    <start_bl_index>`1`</start_bl_index><start_port_index>`1`</start_port_index>
    <end_bl_index>`2`</end_bl_index><end_port_index>`0`</end_port_index>
  </object>
</page></project></Header>"""


def _semantic_data():
    return {
        "Константа": {
            "class": "Константа", "status": "derived",
            "ports": {"model": "fixed", "inputs": [],
                      "outputs": [{"index": 0, "name": "y",
                                   "direction": "out"}]},
            "behavior": {"operation": "constant", "expression": "y = a",
                         "parameters": ["a"],
                         "provenance": {"status": "claim", "ref": "test"}},
            "dependencies": [{
                "output": 0,
                "source": {"kind": "property", "name": "a"},
                "kind": "unconditional",
                "provenance": {"status": "claim", "ref": "test"},
            }],
            "review": {"status": "approved", "reviewer": "test",
                       "date": "2026-10-31"},
        },
        "Усилитель": {
            "class": "Усилитель", "status": "derived",
            "ports": {"model": "fixed",
                      "inputs": [{"index": 0, "name": "u",
                                  "direction": "in"}],
                      "outputs": [{"index": 1, "name": "y",
                                   "direction": "out"}]},
            "behavior": {"operation": "gain", "expression": "y = a * u",
                         "parameters": ["a"],
                         "provenance": {"status": "claim", "ref": "test"}},
            "dependencies": [
                {"output": 1, "source": {"kind": "port", "index": 0},
                 "kind": "unconditional",
                 "provenance": {"status": "claim", "ref": "test"}},
                {"output": 1, "source": {"kind": "property", "name": "a"},
                 "kind": "unconditional",
                 "provenance": {"status": "claim", "ref": "test"}},
            ],
            "review": {"status": "approved", "reviewer": "test",
                       "date": "2026-10-31"},
        },
    }


def _semantic_registry(data=None):
    return BlockContractRegistry({
        "schema": SCHEMA, "version": VERSION,
        "classes": data if data is not None else _semantic_data(),
        "meta": {},
    })


def _chain_to(result, prefix):
    chains = [item for item in result.items
              if item["source"]["address"].startswith(prefix)]
    assert chains, result.items
    return chains[0]


def test_influence_returns_chain_with_functional_hops():
    index = ModelIndex(parse_xprt(MODEL))
    result = influence(index, _semantic_registry(), "main::S:0")
    chain = _chain_to(result, "main::K@property:a")
    assert chain["source"]["kind"] == "property"
    assert [hop["kind"] for hop in chain["hops"]] == [
        "unconditional", "unconditional"]
    assert chain["evidence"]["status"] == "contract"


def test_influence_keeps_each_hop_kind():
    data = copy.deepcopy(_semantic_data())
    data["Усилитель"]["dependencies"][0]["kind"] = "conditional"
    data["Усилитель"]["dependencies"][0]["condition"] = {
        "op": "equals",
        "source": {"kind": "property", "name": "a"},
        "value": 0,
    }
    result = influence(
        ModelIndex(parse_xprt(MODEL)), _semantic_registry(data), "main::S:0")
    chain = _chain_to(result, "main::K@property:a")
    assert [hop["kind"] for hop in chain["hops"]] == [
        "conditional", "unconditional"]


def test_influence_unknown_contract_returns_unknown():
    data = copy.deepcopy(_semantic_data())
    data.pop("Усилитель")
    result = influence(
        ModelIndex(parse_xprt(MODEL)), _semantic_registry(data), "main::S:0")
    assert all(item["evidence"]["status"] != "contract"
               for item in result.items)
    assert any("class_unknown" in item for item in result.unknown)
