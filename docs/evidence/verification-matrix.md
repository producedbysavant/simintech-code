# Матрица проверки фактов

Файл сгенерирован `scripts/evidence.py` из `claims.yaml` — правьте реестр.

`kind` показывает, чем факт подтверждён: `live` — живой прогон,
`distribution` — сверка с поставкой, `unit-pure` — чистый разбор,
`unit-fake` — тест на подделке (контракт кода, не поведение среды).

| id | статус | источник | версия | дата | подтверждение |
|---|---|---|---|---|---|
| `constant-param-is-a` | live-verified | live-com | 2.26.6.23 | 2026-09-10 | `tests/integration/test_lifecycle.py::test_build_simple_model` (live), `tests/unit/test_catalog_dumps.py::test_props_for_keeps_names_from_real_dumps` (distribution) |
| `setblockprop-ignores-unknown-name` | live-verified | live-com | 2.26.6.23 | 2026-09-10 | - |
| `blocks-are-not-renamed-via-com` | live-verified | live-com | 2.26.6.23 | 2026-09-15 | - |
| `summator-ports-need-setportcount` | live-verified | live-com | 2.26.6.23 | 2026-09-15 | `tests/unit/test_block.py::test_set_in_port_count_adds_inputs` (unit-fake) |
| `new-project-does-not-calculate` | live-verified | controlled-experiment | 2.26.6.23 | 2026-09-15 | - |
| `template-project-calculates` | live-verified | controlled-experiment | 2.26.6.23 | 2026-09-15 | - |
| `floating-input-stops-calculation` | live-verified | controlled-experiment | 2.26.6.23 | 2026-09-15 | - |
| `runto-is-not-blocking` | live-verified | controlled-experiment | 2.26.6.23 | 2026-09-15 | - |
| `signals-need-signal-base` | live-verified | live-com | 2.26.6.23 | 2026-09-10 | `tests/integration/test_lifecycle.py::test_signal_by_name_refuses_without_signal_base` (live) |
| `wires-have-no-ends-via-com` | live-verified | live-com | 2.26.6.23 | 2026-09-17 | - |
| `findstartport-is-a-signal-resolver` | contradicted | controlled-experiment | 2.26.6.23 | 2026-09-23 | - |
| `conn-describes-wire-ends-pairwise` | live-verified | controlled-experiment | 2.26.6.23 | 2026-09-23 | `tests/integration/test_topology_live.py::test_vendor_cardinality_rule_makes_the_branch_a_star` (live) |
| `fsm-blocks-need-full-record-name` | live-verified | live-com | 2.26.6.23 | 2026-09-15 | - |
| `block-size-covers-few-classes` | code-confirmed | source-code | 2.26.6.23 | 2026-09-17 | - |
| `semantic-query-and-inspection-agree` | live-verified | live-com | 2.26.6.23 | 2026-09-26 | `tests/integration/test_semantic_live.py::test_query_connections_matches_vendor_reference` (live) |
| `traceallports-second-arg-crosses-container` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | - |
| `wire-node-number-is-point-nmb-plus-one` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | - |
| `savemodeltofile-describes-current-container` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | - |
| `createprimitiv-object-has-no-ports` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | - |
| `createprimitiv-needs-graphic-container` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | - |
| `objects-are-created-only-in-initialization` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | - |
| `submodel-ports-are-created-on-its-page` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | - |
| `tab-is-a-predefined-constant` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | - |
| `script-compile-errors-are-silent-via-com` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | - |
| `savemodeltofile-understands-absolute-path` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | - |
| `createmodelfromfile-did-not-create-objects` | contradicted | live-com | 2.26.6.23 | 2026-09-29 | - |
| `traceallports-order-is-not-a-contract` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | - |
| `branch-point-is-not-a-separate-object` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | - |
| `getparentwire-functions-describe-branching` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | - |
| `getparentwire-functions-return-zero-without-branching` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | - |
| `object-type-constants-are-named` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | - |
| `createblock-creates-by-class-name` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | - |
| `port-index-identity-holds-for-blocks-only` | live-verified | live-com | 2.26.6.23 | 2026-09-28 | `tests/integration/test_topology_live.py::test_port_index_round_trip_is_identity` (live), `tests/integration/test_topology_live.py::test_line_fails_addressing_round_trip` (live) |
| `model-text-function-family-has-four-names` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | - |
| `savemodeltotext-missing-from-distribution` | unknown | source-code | 2.26.6.23 | 2026-09-28 | - |
| `tracestartportwires-walks-service-blocks` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | - |
| `page-script-runs-in-initialization` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | `tests/integration/test_language_contour_live.py::test_body_runs_in_initialization_and_previous_script_returns` (live) |
| `language-literal-uses-chr34-and-clrf` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | `tests/unit/test_model_operations.py::test_literal_escapes_quotes_and_newlines_the_measured_way` (unit-pure) |
| `page-script-readable-without-calculation` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | `tests/integration/test_language_contour_live.py::test_read_page_script_returns_script_and_keeps_model_time` (live) |
| `submodel-script-injection-needs-reinitsubmodel` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | - |
| `initsubmodelports-makes-ports-immediately-visible` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | - |
| `removeprimitiv-breaks-calculation-start` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | - |
| `wire-removal-keeps-calculation-start` | live-verified | live-com | 2.26.6.23 | 2026-10-03 | - |
| `model-text-quote-is-chr34` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | - |
| `model-text-loading-creates-objects` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | - |
| `dot-syntax-belongs-to-model-text` | live-verified | live-com | 2.26.6.23 | 2026-09-29 | - |
| `container-traversal-functions-are-used-by-vendor` | live-verified | xprt-observation | 2.26.6.23 | 2026-09-29 | - |
| `traceallports-second-arg-defaults-true` | vendor-confirmed | vendor | 2.26.6.23 | 2026-09-28 | - |
| `pack-members-are-open-projects` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | - |
| `pack-step-advances-member-time` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | - |
| `packrun-does-not-advance-in-embedding` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | - |
| `pack-member-close-removes-from-pack` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | - |
| `closepack-invalid-id-crashes-server` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | `tests/unit/test_pack.py::test_pack_close_refuses_invalid_id` (unit-fake) |
| `pack-double-open-creates-second-pack` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | - |
| `pack-member-ids-are-unstable` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | - |
| `written-pack-opens-in-simintech` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | `tests/integration/test_pack_writer_live.py::test_written_pack_opens_in_simintech` (live) |
| `page-init-reruns-on-each-step` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | `tests/unit/test_script_bridge.py::test_wait_protocol_is_one_run_and_poll` (unit-fake) |
| `run-outruns-the-first-time-read` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | `tests/unit/test_script_bridge.py::test_wait_reads_baseline_before_run` (unit-fake) |
| `projectstart-executes-init-and-resets-time` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | `tests/unit/test_script_bridge.py::test_probe_starts_before_run_and_only_once` (unit-fake) |
| `endtime-run-executes-init-without-growth` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | - |
| `langblock-port-array-without-size` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | - |
| `block-points-first-is-center` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | - |
| `block-ports-at-center-row` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | - |
| `block-set-center-is-exact` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | - |
| `constlabel-objects-are-anchors` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | - |
| `com-release-does-not-terminate-server` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | - |
| `com-shutdown-on-last-release-is-not-a-mechanism` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | - |
| `com-createobject-attaches-to-manual-instance` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | - |
| `com-session-ownership-and-managed-shutdown` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | `tests/integration/test_lifecycle.py::test_connect_disconnect` (live) |
| `job-object-reaps-owned-process-on-owner-death` | live-verified | live-com | 2.26.6.23 | 2026-10-02 | - |
| `mstarter-macros-runs-macro-in-a-new-instance` | live-verified | controlled-experiment | 2.26.6.23 | 2026-10-06 | `tests/unit/test_cli_runner.py::test_run_macro_via_starter_builds_vendor_command` (unit-pure) |
| `projmacros-does-not-run-macro-and-keeps-process-alive` | live-verified | controlled-experiment | 2.26.6.23 | 2026-10-06 | - |
| `openproject-succeeds-on-missing-path` | live-verified | live-com | 2.26.6.23 | 2026-10-03 | - |
| `no-block-deletion-in-com-api` | code-confirmed | source-code | - | - | - |
| `setpagescript-returns-one-always` | live-verified | live-com | 2.26.6.23 | 2026-09-21 | - |
| `no-getpagescript-in-com-api` | code-confirmed | source-code | - | - | - |
| `com-cannot-list-block-properties` | code-confirmed | source-code | - | - | - |
| `catalog-provenance-unknown` | unknown | source-code | - | - | - |
| `catalog-failed-classes-not-created` | code-confirmed | source-code | - | - | - |
| `createmodel-not-in-vendor-help` | live-verified | live-com | 2.26.9.29 | 2026-10-16 | - |
| `bridge-identifies-its-page-by-snapshot` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | `tests/integration/test_topology_live.py::test_reading_topology_inside_container_keeps_its_script` (live) |
| `live-tests-run-only-locally` | code-confirmed | source-code | - | - | - |
| `project-restart-group-unverified` | unknown | source-code | - | - | - |
| `submodel-load-assign-unverified` | unknown | source-code | - | - | - |
| `wire-branch-to-unverified` | unknown | source-code | - | - | - |
| `comclient-project-enumeration-unverified` | unknown | source-code | - | - | - |
| `pack-run-to-semantics-unverified` | unknown | source-code | - | - | - |
| `topology-goes-blind-after-removals` | live-verified | live-com | 2.26.6.23 | 2026-10-06 | - |
| `predicted-polyline-is-normalizewire-shape` | code-confirmed | source-code | - | - | - |
| `backward-links-not-predicted` | code-confirmed | source-code | - | - | - |
| `channel-track-order-is-model` | code-confirmed | source-code | - | - | - |
| `far-link-midpoint-vertical-live` | live-verified | live-com | 2.26.9.29 | 2026-10-08 | - |
| `normalize-fills-empty-routes` | live-verified | live-com | 2.26.6.23 | 2026-10-04 | - |
| `normalize-does-not-repair-filled-routes` | live-verified | live-com | 2.26.9.29 | 2026-10-10 | - |
| `baked-import-wire-geometry-not-repairable` | live-verified | live-com | 2.26.9.29 | 2026-10-10 | - |
| `node-limit-three-lines` | live-verified | live-com | 2.26.9.29 | 2026-10-08 | - |
| `empty-branch-pair-0-0i` | live-verified | live-com | 2.26.9.29 | 2026-10-08 | - |
| `branch-k-outside-points-silently-collapses` | code-confirmed | source-code | - | - | - |
| `screenshot-canvas-is-window` | live-verified | live-com | 2.26.9.29 | 2026-10-08 | - |
| `screenshot-zoom-tiles` | live-verified | live-com | 2.26.9.29 | 2026-10-08 | - |
| `mcp-failure-is-exception` | code-confirmed | source-code | - | - | - |
| `mcp-error-prefix-contract` | code-confirmed | source-code | - | - | - |
| `mcp-contract-drift-logging` | code-confirmed | source-code | - | - | - |
| `mcp-single-com-thread` | code-confirmed | source-code | - | - | - |
| `mcp-com-timeout-not-interrupting` | live-verified | live-com | 2.26.6.23 | 2026-09-17 | - |
| `mcp-stuck-call-instant-refusal` | live-verified | live-com | 2.26.9.29 | 2026-10-08 | - |
| `mcp-contour-reads-shift-model-time` | code-confirmed | source-code | - | - | - |
| `mcp-ownership-gate-fail-closed` | code-confirmed | source-code | - | - | - |
| `mcp-project-change-only-via-set-project` | code-confirmed | source-code | - | - | - |
| `mcp-pack-member-protection` | live-verified | live-com | 2.26.6.23 | 2026-10-01 | - |
| `mcp-session-scene-degradation` | live-verified | live-com | 2.26.6.23 | 2026-10-06 | - |
| `mcp-save-atomic-temp-file` | live-verified | live-com | 2.26.9.29 | 2026-10-08 | - |
| `mcp-mutation-note` | code-confirmed | source-code | - | - | - |
| `mcp-mutating-set-is-contract` | code-confirmed | source-code | - | - | - |
| `mcp-sandbox-limit-before-read` | code-confirmed | source-code | - | - | - |
| `mcp-sandbox-env-fail-closed` | code-confirmed | source-code | - | - | - |
| `mcp-every-tool-wrapped` | code-confirmed | source-code | - | - | - |
| `mcp-plain-tools-exactly-eight` | code-confirmed | source-code | - | - | - |
| `mcp-tool-annotations-contract` | code-confirmed | source-code | - | - | - |
| `mcp-readme-counts-contract` | code-confirmed | source-code | - | - | - |
| `mcp-contour-core-single-entry` | code-confirmed | source-code | - | - | - |
| `model-ir-xprt-wire-endpoints` | live-verified | xprt-observation | not recorded in source file | 2026-10-28 | `tests/unit/test_model_ir_xprt.py::test_wire_and_branch_resolve_to_objects_and_ports` (unit-pure) |
| `model-ir-blockimage-is-decoration` | live-verified | xprt-observation | not recorded in source file | 2026-10-28 | `tests/unit/test_model_ir_xprt.py::test_submodel_page_is_container_and_blockimage_is_excluded` (unit-pure) |
| `model-ir-wire-names-are-not-identity` | live-verified | xprt-observation | not recorded in source file | 2026-10-28 | `tests/unit/test_model_ir_xprt_edges.py::test_duplicate_names_get_distinct_addresses_and_info` (unit-pure) |
| `model-ir-hashes-exclude-volatile` | code-confirmed | source-code | - | - | `tests/unit/test_model_ir_xprt.py::test_properties_scripts_and_volatile_values` (unit-pure) |
| `model-ir-xprt-streaming-limits` | code-confirmed | source-code | - | - | `tests/unit/test_model_ir_xprt_edges.py::test_broken_xml_is_refusal_not_empty_model` (unit-pure) |
| `model-ir-numbered-tags` | code-confirmed | source-code | - | - | `tests/unit/test_model_ir_xprt_edges.py::test_numbered_object_tags_keep_order_and_wires` (unit-pure) |
| `model-ir-text-source-synthetic-ports` | code-confirmed | source-code | - | - | `tests/unit/test_model_ir_text.py::test_text_model_builds_containers_objects_and_synthetic_ports` (unit-pure) |
| `model-ir-merge-primary-xprt` | code-confirmed | source-code | - | - | `tests/unit/test_model_ir_merge.py::test_class_mismatch_is_strict_refusal` (unit-pure) |
| `model-ir-topology-edge-only` | code-confirmed | source-code | - | - | `tests/unit/test_model_ir_topology.py::test_topology_to_ir_builds_objects_ports_and_edges` (unit-pure) |
| `model-ir-signal-graph-block-edges` | code-confirmed | source-code | - | - | `tests/unit/test_model_ir_graph.py::test_inspect_trace_path_and_ancestors` (unit-pure) |
| `model-ir-manifest-budget` | code-confirmed | source-code | - | - | `tests/unit/test_model_ir_manifest.py::test_manifest_omits_what_does_not_fit` (unit-pure) |
| `model-ir-query-evidence` | code-confirmed | source-code | - | - | `tests/unit/test_model_ir_graph.py::test_find_objects_compare_and_unknown_query` (unit-pure) |
