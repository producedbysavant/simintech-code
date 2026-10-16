# Матрица проверки фактов

Файл сгенерирован `scripts/evidence.py` из `claims.yaml` — правьте реестр.

`kind` показывает, чем факт подтверждён: `live` — живой прогон,
`distribution` — сверка с поставкой, `unit-pure` — чистый разбор,
`unit-fake` — тест на подделке (контракт кода, не поведение среды).

| id | статус | источник | версия | дата | подтверждение |
|---|---|---|---|---|---|
| `constant-param-is-a` | live-verified | live-com | 2.26.6.23 | 2026-09-10 | `tests/integration/test_lifecycle.py::test_build_simple_model` (live), `tests/unit/test_catalog_dumps.py::test_props_for_keeps_names_from_real_dumps` (distribution) |
| `setblockprop-ignores-unknown-name` | live-verified | live-com | 2.26.6.23 | 2026-09-10 | — |
| `blocks-are-not-renamed-via-com` | live-verified | live-com | 2.26.6.23 | 2026-09-15 | — |
| `summator-ports-need-setportcount` | live-verified | live-com | 2.26.6.23 | 2026-09-15 | `tests/unit/test_block.py::test_set_in_port_count_adds_inputs` (unit-fake) |
| `new-project-does-not-calculate` | live-verified | controlled-experiment | 2.26.6.23 | 2026-09-15 | — |
| `template-project-calculates` | live-verified | controlled-experiment | 2.26.6.23 | 2026-09-15 | — |
| `floating-input-stops-calculation` | live-verified | controlled-experiment | 2.26.6.23 | 2026-09-15 | — |
| `runto-is-not-blocking` | live-verified | controlled-experiment | 2.26.6.23 | 2026-09-15 | — |
| `signals-need-signal-base` | live-verified | live-com | 2.26.6.23 | 2026-09-10 | `tests/integration/test_lifecycle.py::test_signal_by_name_refuses_without_signal_base` (live) |
| `wires-have-no-ends-via-com` | live-verified | live-com | 2.26.6.23 | 2026-09-17 | — |
| `findstartport-is-a-signal-resolver` | contradicted | controlled-experiment | 2.26.6.23 | 2026-09-23 | — |
| `conn-describes-wire-ends-pairwise` | live-verified | controlled-experiment | 2.26.6.23 | 2026-09-23 | `tests/integration/test_topology_live.py::test_vendor_cardinality_rule_makes_the_branch_a_star` (live) |
| `fsm-blocks-need-full-record-name` | live-verified | live-com | 2.26.6.23 | 2026-09-15 | — |
| `block-size-covers-few-classes` | code-confirmed | source-code | 2.26.6.23 | 2026-09-17 | — |
| `semantic-query-and-inspection-agree` | live-verified | live-com | 2.26.6.23 | 2026-09-26 | `tests/integration/test_semantic_live.py::test_query_connections_matches_vendor_reference` (live) |
| `traceallports-second-arg-crosses-container` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | — |
| `wire-node-number-is-point-nmb-plus-one` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | — |
| `savemodeltofile-describes-current-container` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | — |
| `createprimitiv-object-has-no-ports` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | — |
| `createprimitiv-needs-graphic-container` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | — |
| `objects-are-created-only-in-initialization` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | — |
| `submodel-ports-are-created-on-its-page` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | — |
| `tab-is-a-predefined-constant` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | — |
| `script-compile-errors-are-silent-via-com` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | — |
| `savemodeltofile-understands-absolute-path` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | — |
| `createmodelfromfile-did-not-create-objects` | contradicted | live-com | 2.26.6.23 | 2026-09-29 | — |
| `traceallports-order-is-not-a-contract` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | — |
| `branch-point-is-not-a-separate-object` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | — |
| `getparentwire-functions-describe-branching` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | — |
| `getparentwire-functions-return-zero-without-branching` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | — |
| `object-type-constants-are-named` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | — |
| `createblock-creates-by-class-name` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | — |
| `port-index-identity-holds-for-blocks-only` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | `tests/integration/test_topology_live.py::test_port_index_round_trip_is_identity` (live), `tests/integration/test_topology_live.py::test_line_fails_addressing_round_trip` (live) |
| `model-text-function-family-has-four-names` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | — |
| `savemodeltotext-missing-from-distribution` | unknown | source-code | 2.26.6.23 | 2026-09-28 | — |
| `tracestartportwires-walks-service-blocks` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | — |
| `page-script-runs-in-initialization` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | `tests/integration/test_language_contour_live.py::test_body_runs_in_initialization_and_previous_script_returns` (live) |
| `language-literal-uses-chr34-and-clrf` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | `tests/unit/test_model_operations.py::test_literal_escapes_quotes_and_newlines_the_measured_way` (unit-pure) |
| `page-script-readable-without-calculation` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | `tests/integration/test_language_contour_live.py::test_read_page_script_returns_script_and_keeps_model_time` (live) |
| `submodel-script-injection-needs-reinitsubmodel` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | — |
| `initsubmodelports-makes-ports-immediately-visible` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | — |
| `removeprimitiv-breaks-calculation-start` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | — |
| `wire-removal-keeps-calculation-start` | live-verified | live-com | 2.26.6.23 | 2026-10-03 | — |
| `model-text-quote-is-chr34` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | — |
| `model-text-loading-creates-objects` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | — |
| `dot-syntax-belongs-to-model-text` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | — |
| `container-traversal-functions-are-used-by-vendor` | live-verified | xprt-observation | 2.26.6.23 | 2026-09-29 | — |
| `traceallports-second-arg-defaults-true` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | — |
| `pack-members-are-open-projects` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | — |
| `pack-step-advances-member-time` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | — |
| `packrun-does-not-advance-in-embedding` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | — |
| `pack-member-close-removes-from-pack` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | — |
| `closepack-invalid-id-crashes-server` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | `tests/unit/test_pack.py::test_pack_close_refuses_invalid_id` (unit-fake) |
| `pack-double-open-creates-second-pack` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | — |
| `pack-member-ids-are-unstable` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | — |
| `written-pack-opens-in-simintech` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | `tests/integration/test_pack_writer_live.py::test_written_pack_opens_in_simintech` (live) |
| `page-init-reruns-on-each-step` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | `tests/unit/test_script_bridge.py::test_wait_protocol_is_one_run_and_poll` (unit-fake) |
| `run-outruns-the-first-time-read` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | `tests/unit/test_script_bridge.py::test_wait_reads_baseline_before_run` (unit-fake) |
| `projectstart-executes-init-and-resets-time` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | `tests/unit/test_script_bridge.py::test_probe_starts_before_run_and_only_once` (unit-fake) |
| `endtime-run-executes-init-without-growth` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | — |
| `langblock-port-array-without-size` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | — |
| `block-points-first-is-center` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | — |
| `block-ports-at-center-row` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | — |
| `block-set-center-is-exact` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | — |
| `constlabel-objects-are-anchors` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | — |
| `com-release-does-not-terminate-server` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | — |
| `com-shutdown-on-last-release-is-not-a-mechanism` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | — |
| `com-createobject-attaches-to-manual-instance` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | — |
| `com-session-ownership-and-managed-shutdown` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | `tests/integration/test_lifecycle.py::test_connect_disconnect` (live) |
| `job-object-reaps-owned-process-on-owner-death` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | — |
| `mstarter-macros-runs-macro-in-a-new-instance` | live-verified | controlled-experiment | 2.26.6.23 | 2026-10-06 | `tests/unit/test_cli_runner.py::test_run_macro_via_starter_builds_vendor_command` (unit-pure) |
| `projmacros-does-not-run-macro-and-keeps-process-alive` | live-verified | controlled-experiment | 2.26.6.23 | 2026-10-06 | — |
