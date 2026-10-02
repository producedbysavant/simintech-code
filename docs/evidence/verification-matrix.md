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
| `semantic-query-and-inspection-agree` | verified | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-26 | `tests/integration/test_semantic_live.py::test_query_connections_matches_vendor_reference` (live) |
| `traceallports-second-arg-crosses-container` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `wire-node-number-is-point-nmb-plus-one` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `savemodeltofile-describes-current-container` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `createprimitiv-object-has-no-ports` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `createprimitiv-needs-graphic-container` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `objects-are-created-only-in-initialization` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `submodel-ports-are-created-on-its-page` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `tab-is-a-predefined-constant` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `script-compile-errors-are-silent-via-com` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `savemodeltofile-understands-absolute-path` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `createmodelfromfile-did-not-create-objects` | refuted | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-29 | — |
| `traceallports-order-is-not-a-contract` | verified | official-doc | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `branch-point-is-not-a-separate-object` | verified | official-doc | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `getparentwire-functions-describe-branching` | verified | official-doc | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `getparentwire-functions-return-zero-without-branching` | verified | official-doc | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `object-type-constants-are-named` | verified | official-doc | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `createblock-creates-by-class-name` | verified | official-doc | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `port-index-identity-holds-for-blocks-only` | verified | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | `tests/integration/test_topology_live.py::test_port_index_round_trip_is_identity` (live), `tests/integration/test_topology_live.py::test_line_fails_addressing_round_trip` (live) |
| `model-text-function-family-has-four-names` | verified | official-doc | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `savemodeltotext-missing-from-distribution` | unknown | source-code | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `tracestartportwires-walks-service-blocks` | verified | official-doc | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `page-script-runs-in-initialization` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-29 | `tests/integration/test_language_contour_live.py::test_body_runs_in_initialization_and_previous_script_returns` (live) |
| `language-literal-uses-chr34-and-clrf` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-29 | `tests/unit/test_model_operations.py::test_literal_escapes_quotes_and_newlines_the_measured_way` (unit) |
| `page-script-readable-without-calculation` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-29 | `tests/integration/test_language_contour_live.py::test_read_page_script_returns_script_and_keeps_model_time` (live) |
| `submodel-script-injection-needs-reinitsubmodel` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-29 | — |
| `initsubmodelports-makes-ports-immediately-visible` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-29 | — |
| `removeprimitiv-breaks-calculation-start` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-29 | — |
| `model-text-quote-is-chr34` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-29 | — |
| `model-text-loading-creates-objects` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-29 | — |
| `dot-syntax-belongs-to-model-text` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-09-29 | — |
| `container-traversal-functions-are-used-by-vendor` | measured | xprt-observation | SimInTech64, поставка 2.26.6.23 | 2026-09-29 | — |
| `traceallports-second-arg-defaults-true` | verified | official-doc | SimInTech64, поставка 2.26.6.23 | 2026-09-28 | — |
| `pack-members-are-open-projects` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-01 | — |
| `pack-step-advances-member-time` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-01 | — |
| `packrun-does-not-advance-in-embedding` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-01 | — |
| `pack-member-close-removes-from-pack` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-01 | — |
| `closepack-invalid-id-crashes-server` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-01 | `tests/unit/test_pack.py::test_pack_close_refuses_invalid_id` (unit) |
| `pack-double-open-creates-second-pack` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-01 | — |
| `pack-member-ids-are-unstable` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-01 | — |
| `written-pack-opens-in-simintech` | verified | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-01 | `tests/integration/test_pack_writer_live.py::test_written_pack_opens_in_simintech` (live) |
| `page-init-reruns-on-each-step` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-01 | `tests/unit/test_script_bridge.py::test_wait_protocol_is_one_run_and_poll` (unit) |
| `run-outruns-the-first-time-read` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-01 | `tests/unit/test_script_bridge.py::test_wait_reads_baseline_before_run` (unit) |
| `projectstart-executes-init-and-resets-time` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-01 | `tests/unit/test_script_bridge.py::test_probe_starts_before_run_and_only_once` (unit) |
| `endtime-run-executes-init-without-growth` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-01 | — |
| `langblock-port-array-without-size` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-02 | — |
| `block-points-first-is-center` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-02 | — |
| `block-ports-at-center-row` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-02 | — |
| `block-set-center-is-exact` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-02 | — |
| `constlabel-objects-are-anchors` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-02 | — |
| `com-release-does-not-terminate-server` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-02 | — |
| `com-shutdown-on-last-release-is-not-a-mechanism` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-02 | — |
| `com-createobject-attaches-to-manual-instance` | measured | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-02 | — |
| `com-session-ownership-and-managed-shutdown` | verified | live-com | SimInTech64, поставка 2.26.6.23 | 2026-10-02 | `tests/integration/test_lifecycle.py::test_connect_disconnect` (live) |
