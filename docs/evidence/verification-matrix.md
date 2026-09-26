# Матрица проверки утверждений

Файл сгенерирован `scripts/evidence.py` из `claims.yaml` — правьте реестр.

`kind` показывает, чем утверждение подтверждено: `live` — живой прогон,
`distribution` — сверка с поставкой, `unit` — тест на подделке (контракт
кода, не поведение среды).

| id | статус | источник | версия | дата | подтверждение |
|---|---|---|---|---|---|
| `constant-param-is-a` | verified | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-10 | `tests/integration/test_lifecycle.py::test_build_simple_model` (live), `tests/unit/test_catalog_dumps.py::test_props_for_keeps_names_from_real_dumps` (distribution) |
| `setblockprop-ignores-unknown-name` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-10 | — |
| `blocks-are-not-renamed-via-com` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-15 | — |
| `summator-ports-need-setportcount` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-15 | `tests/unit/test_block.py::test_set_in_port_count_adds_inputs` (unit) |
| `new-project-does-not-calculate` | measured | controlled-experiment | SimInTech64, поставка 2.26.6.23 | 2026-09-15 | — |
| `template-project-calculates` | measured | controlled-experiment | SimInTech64, поставка 2.26.6.23 | 2026-09-15 | — |
| `floating-input-stops-calculation` | measured | controlled-experiment | SimInTech64, поставка 2.26.6.23 | 2026-09-15 | — |
| `runto-is-not-blocking` | measured | controlled-experiment | SimInTech64, поставка 2.26.6.23 | 2026-09-15 | — |
| `signals-need-signal-base` | verified | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-10 | `tests/integration/test_lifecycle.py::test_signal_by_name_refuses_without_signal_base` (live) |
| `wires-have-no-ends-via-com` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-17 | — |
| `findstartport-is-a-signal-resolver` | refuted | controlled-experiment | SimInTech64, поставка 2.26.6.23 | 2026-09-23 | — |
| `conn-describes-wire-ends-pairwise` | verified | controlled-experiment | SimInTech64, поставка 2.26.6.23 | 2026-09-23 | `tests/integration/test_topology_live.py::test_vendor_cardinality_rule_makes_the_branch_a_star` (live) |
| `fsm-blocks-need-full-record-name` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-15 | — |
| `block-size-covers-few-classes` | measured | source-code | SimInTech64, поставка 2.26.6.23 | 2026-09-17 | — |
