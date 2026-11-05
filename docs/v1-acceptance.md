# v1 acceptance traceability

Every acceptance criterion in [spec §11](specs/2026-11-01-email-assistant-v1-design.md#11-acceptance-criteria),
the tests that prove it, where they run, and their status. Part of the v1 release gate (#100).

Checked on 2026-11-04 against `main` at `d5d6d47` (README for the v1 architecture, #186).

## Where tests run

- **backend CI**: `ci.yml` job `backend`, `uv run pytest` against MongoDB and GreenMail service containers. Paths
  below are relative to `backend/`.
- **frontend CI**: `ci.yml` job `frontend`, `npx vitest run` (the `*.integration.test.ts` files use a real
  MongoDB). Paths relative to `frontend/`.
- **e2e CI**: `ci.yml` job `e2e`, Playwright against the real FastAPI + Next stack, MongoDB and GreenMail.
- **weekly metrics workflow**: `metrics.yml`, the metrics command with the paid AI over the committed synthetic test
  set. Needs the `ANTHROPIC_API_KEY` repository secret, which isn't set yet, so it has never run.
- **owner-only local run**: needs the owner's accounts or machines (a disposable Gmail account, the Windows machine
  that runs Proton Bridge, or the owner's real test set).

## Status values

- **green in CI**: the tests listed passed in `main`'s CI at `d5d6d47` (run 41949980876: backend 818 passed, 17 skipped, none
  failed; Vitest 105/105; Playwright 17/17). CI runs pytest with `-q`, so the backend names were confirmed in a local
  `pytest -rA` run of the same commit. The new AC-1.2 conformance test first runs in CI on the PR that adds it.
- **pending owner run**: the CI tests cover all of the logic, but the criterion as written also needs something only
  the owner can do: a run on their accounts or machines, or adding a repository secret. The command or issue is given.
- **GAP**: no test proves it. (There are none.)

## Table

| AC | Criterion | Test(s) | Runs in | Status |
|---|---|---|---|---|
| AC-1.1 | Running every conformance tool loses no seeded message, for any plugin | `tests/conformance/test_mailbox_conformance.py::test_running_every_tool_loses_no_message[reference-imap]`, `[proton]`, `[gmail]` | backend CI (reference-imap, proton); owner-only local run (gmail) | green in CI for reference-imap and proton; Gmail **pending owner run** (#96): `GMAIL_ADDRESS=… GMAIL_APP_PASSWORD=… uv run pytest tests/conformance -k gmail` |
| AC-1.2 | No delete/expunge tool exists and no source path permanently removes a message | `tests/conformance/test_no_permanent_remove.py::test_no_source_path_permanently_removes_a_message`, `::test_detector_flags_unscoped_expunge`, `::test_reference_plugin_offers_no_destructive_tool`; `tests/conformance/test_mailbox_conformance.py::test_no_tool_is_named_like_a_permanent_remove[reference-imap]`, `[proton]` (added for this gate; the `[gmail]` case runs only live, but Gmail's tools come from the same `imap_mailbox` server plus a read-only `setup_warnings`) | backend CI | green in CI |
| AC-1.3 | `archive` with `verified=false` keeps the job open, the mail in the inbox, and names the plugin | `tests/test_executor.py::test_an_unverified_or_garbled_archive_keeps_the_job_open_and_names_the_plugin`, `::test_a_disconnected_plugin_keeps_the_job_open_and_names_it`; `src/__tests__/page.test.tsx` "lists each open job with sender, subject, first evidence quote, error and reminder" | backend CI, frontend CI | green in CI |
| AC-2.1 | A message on two jobs stays in the inbox until both are done or dismissed | `tests/test_executor.py::test_a_message_stays_until_every_job_on_it_is_final` | backend CI | green in CI |
| AC-2.2 | A failed `send` doesn't archive, and the job shows "send failed — retry" | `tests/test_send.py::test_a_reply_whose_send_fails_stays_open_to_retry_and_isnt_archived`; `src/__tests__/page.test.tsx` "an approval that comes back failed stays in the queue with its error" | backend CI, frontend CI | green in CI |
| AC-2.3 | A sender corrected to noise stays noise across 10 repeats | `tests/test_routes/test_corrections_api.py::test_ac_2_3_mail_from_a_sender_corrected_to_noise_is_handled_as_noise_across_ten_repeats[ask]`, `[autonomous]` | backend CI | green in CI |
| AC-2.4 | Restoring mail the app archived creates a rule so the next similar one waits | `tests/test_routes/test_restore_learning_api.py::test_ac_2_4_restoring_mail_the_app_archived_makes_the_next_similar_message_wait_for_the_owner`, `::test_a_late_copy_of_restored_mail_waits_for_the_owner_instead_of_being_archived` | backend CI | green in CI |
| AC-3.1 | Every evidence quote appears verbatim in the source message | `tests/test_pipeline/test_validate.py::test_a_valid_proposal_becomes_a_job_with_its_artifacts`, `::test_each_failed_check_is_named` (its "evidence not in the email" case) | backend CI | green in CI |
| AC-3.2 | Every non-noise job has a step-saving artifact; otherwise the ask-owner card | `tests/test_pipeline/test_validate.py::test_a_valid_proposal_becomes_a_job_with_its_artifacts`, `::test_a_failing_proposal_becomes_an_ask_owner_job_and_never_a_guess`; `e2e/ask-owner.spec.ts` "the owner picks a verb for mail the app would not guess about" | backend CI, e2e CI | green in CI |
| AC-3.3 | No verb over 50% of non-noise proposals; at least 70% accepted unchanged | Thresholds: `tests/test_metrics.py::test_ac_3_3_no_verb_may_pass_half_of_the_non_noise_proposals`, `::test_ac_3_3_seventy_percent_of_non_noise_proposals_are_the_owners_verb`. Measurement: `uv run python -m app.metrics tests/fixtures/synthetic_test_set.jsonl` | backend CI (thresholds); weekly metrics workflow and owner-only local run (measurement) | **pending owner run**: add the `ANTHROPIC_API_KEY` secret and dispatch `metrics.yml`; locally `uv run python -m app.metrics ../config/test_set.jsonl` over the owner's real set |
| AC-3.4 | No scheduling job for mail without meeting or time language | Threshold: `tests/test_metrics.py::test_ac_3_4_no_scheduling_job_for_mail_without_meeting_or_time_language`. Measurement: as AC-3.3 | as AC-3.3 | **pending owner run** (as AC-3.3) |
| AC-4.1 | At most 2% of "needs me" mail classified as noise | Threshold: `tests/test_metrics.py::test_ac_4_1_at_most_two_percent_of_needs_me_mail_is_classified_as_noise`. Measurement: as AC-3.3 | as AC-3.3 | **pending owner run** (as AC-3.3) |
| AC-4.2 | At least 80% of owner-marked noise classified as noise, after calibration | Threshold: `tests/test_metrics.py::test_ac_4_2_eighty_percent_of_owner_marked_noise_is_classified_as_noise`, `::test_each_line_is_decided_with_the_owners_other_reactions_as_examples`. Measurement: as AC-3.3 | as AC-3.3 | **pending owner run** (as AC-3.3) |
| AC-4.3 | One command reports both metrics; CI runs it on a committed synthetic set | `tests/test_metrics.py::test_one_command_reports_every_metric_and_fails_on_any_fail`; `tests/test_synthetic_test_set.py::test_the_metrics_command_reports_every_metric_over_it`, `::test_every_verb_and_metric_has_a_meaningful_denominator`; `.github/workflows/metrics.yml` | backend CI (the command); weekly metrics workflow (CI over the synthetic set) | **pending owner run**: the workflow fails until the `ANTHROPIC_API_KEY` repository secret is added |
| AC-P.1 | Stopped Bridge is restarted on the next check; the app shows "Bridge restarted"; mail within 5 minutes | `tests/plugins/test_proton_watchdog.py::test_stopped_bridge_is_restarted_on_the_next_check`; `tests/test_plugins/test_diagnosis.py::test_healthy_plugin_after_a_watchdog_restart_says_bridge_restarted`, `::test_bridge_restarting_is_reported_from_the_watchdog` | backend CI; owner-only local run | logic green in CI; **pending owner run** on the Bridge machine with the installed watchdog (#49): stop Bridge, confirm "Bridge restarted" and new mail within 5 minutes |
| AC-P.2 | Killed plugin is restarted; Connections shows "plugin down → restarting" | `tests/plugins/test_proton_watchdog.py::test_killed_plugin_is_restarted`; `tests/test_plugins/test_diagnosis.py::test_plugin_down_while_watchdog_restarts_it`; `src/__tests__/connections-page.test.tsx` "shows one row per plugin: healthy, refused with why, and a repair in progress" | backend CI, frontend CI | green in CI |
| AC-P.3 | Machine offline shows "machine offline"; on return, catch-up with no duplicates or misses | `tests/test_plugins/test_diagnosis.py::test_machine_offline_is_not_reported_as_bridge_down`; `tests/test_sync/test_inbox_sync.py::test_catches_up_after_an_outage_with_no_duplicates_or_missed_mail`; `src/__tests__/connections-page.test.tsx` "names each state plainly, and shows the last sync when there is one" | backend CI, frontend CI | green in CI |
| AC-P.4 | Re-login needed: exact instruction, restarts stop, re-check within 1 minute of the fix | `tests/plugins/test_proton_watchdog.py::test_owner_only_failure_stops_automatic_restarts`; `tests/test_plugins/test_diagnosis.py::test_owner_only_failure_shows_the_exact_instruction`, `::test_refresh_reconnects_a_failed_plugin_within_one_cycle` (one cycle is `REFRESH_SECONDS = 60`) | backend CI | green in CI |
| AC-P.5 | After a reboot and login, watchdog, Bridge and plugin run with no owner action; until then "waiting for login" | `tests/test_plugins/test_diagnosis.py::test_machine_up_without_watchdog_is_waiting_for_login`; `tests/plugins/test_proton_plugin.py::test_settings_load_from_the_env_file_the_logon_task_points_at` | backend CI; owner-only local run | message green in CI; **pending owner run**: install the at-logon task and reboot the Bridge machine (#49) |
| AC-K.1 | With `reply: ask`, no reply is sent without an owner tap | `tests/test_permissions.py::test_a_reply_set_to_ask_is_never_sent_without_a_tap`; `e2e/job-queue.spec.ts` "approving a reply sends the draft and removes the card" | backend CI, e2e CI | green in CI |
| AC-K.2 | With `archive_noise: autonomous`, noise is archived without a tap, in History and Filtered, with a working undo | `tests/test_permissions.py::test_autonomous_noise_is_archived_without_a_tap`; `tests/test_routes/test_history_api.py::test_an_autonomous_archive_is_logged_as_the_apps_with_its_level`, `::test_archive_then_undo_returns_the_message_to_the_inbox_and_logs_both`; `tests/test_routes/test_filtered_api.py::test_ac_k_2_noise_archived_on_its_own_is_listed_in_filtered_and_restore_returns_it`; `e2e/filtered.spec.ts` "noise archived from the queue is listed in Filtered, and Restore returns it to the inbox"; `e2e/history.spec.ts` "a sent reply cannot be unsent, and undoing its archive puts the mail back in the inbox" | backend CI, e2e CI | green in CI |
| AC-K.3 | `unsubscribe` or `forward` set to `autonomous` (file or UI) is rejected with the ceiling explained | `tests/test_permissions.py::test_a_file_above_a_ceiling_or_malformed_is_rejected_with_the_reason`; `tests/test_routes/test_permissions_api.py::test_a_choice_the_ceilings_dont_allow_is_rejected_with_the_reason`; `src/__tests__/permissions-section.test.tsx` "shows why a choice above the ceiling is rejected and keeps the level (AC-K.3 UI half)" | backend CI, frontend CI | green in CI |
| AC-K.4 | After 10 unedited approvals in a row, promotion is offered once; nothing changes unless accepted | `tests/test_routes/test_permissions_api.py::test_ten_unedited_approvals_in_a_row_offer_promotion_once`, `::test_accepting_promotes_and_declining_doesnt_and_neither_offers_again`; `src/__tests__/permissions-section.test.tsx` "offers promotion and only changes the level when the owner accepts (AC-K.4)", "declining keeps the level" | backend CI, frontend CI | green in CI |
| AC-R.1 | In `redacted_cloud`, the AI request has no addresses, phones, URLs or names; the job has the real values | `tests/test_routes/test_privacy_mode_api.py::test_ac_r1_the_ai_request_holds_no_personal_details_and_the_owners_job_holds_the_real_ones` | backend CI | green in CI |
| AC-R.2 | In `full_cloud`, the AI sees minimized content only (no quoted history or signatures) | `tests/test_pipeline/test_propose.py::test_the_ai_request_carries_only_minimized_content`; `tests/test_pipeline/test_minimize.py::test_minimized_text_keeps_the_new_content_and_drops_history_signatures_and_tracking` | backend CI | green in CI |
| AC-C.1 | A new plugin entry in the config appears on Connections after a restart, with no code change | `tests/test_plugins/test_plugin_registry.py::test_new_config_entry_connects_with_no_code_change`, `::test_app_connects_configured_plugins_on_startup`, `::test_connections_lists_every_configured_plugin_with_its_state` | backend CI | green in CI |
| AC-C.2 | A plugin on an unsupported `contract_version` is refused, with the reason shown | `tests/test_plugins/test_plugin_registry.py::test_unsupported_contract_version_is_refused_with_reason`, `::test_connections_lists_every_configured_plugin_with_its_state`; `src/__tests__/connections-page.test.tsx` "shows one row per plugin: healthy, refused with why, and a repair in progress" | backend CI, frontend CI | green in CI |
| AC-C.3 | Both v1 plugins pass the conformance suite | `tests/conformance/test_mailbox_conformance.py` (every test) `[proton]` and `[gmail]` | backend CI (proton, over a TLS fake Bridge in front of GreenMail); owner-only local run (gmail) | Proton green in CI; **pending owner run** for Gmail (#96): `GMAIL_ADDRESS=… GMAIL_APP_PASSWORD=… uv run pytest tests/conformance -k gmail` on a disposable account |
| AC-A.1 | Without a session every route except health and auth is 401; no route takes `user_id` | `tests/test_routes/test_auth_required.py::test_route_without_token_is_401`, `::test_bad_token_is_401`, `::test_no_route_accepts_a_user_id`, `::test_user_id_query_param_cannot_switch_user`, `::test_routes_are_enumerated`, `::test_health_route_is_public` | backend CI | green in CI |
| AC-A.2 | Once an owner exists, sign-up is unavailable | `src/__tests__/auth.integration.test.ts` "given an owner exists, the sign-up API refuses a second account", "given two sign-ups racing on an empty database, only one owner is created"; `src/__tests__/sign-in-page.test.tsx` "given an owner exists, shows sign-in only" | frontend CI (sign-up is Better Auth in the Next app, not a FastAPI route) | green in CI |

## Summary

- **30 criteria.** 21 green in CI, 9 pending an owner run, 0 gaps.
- Pending owner runs, grouped by what unblocks them:
  - **`ANTHROPIC_API_KEY` repository secret**, then dispatch the Metrics workflow: AC-3.3, AC-3.4, AC-4.1, AC-4.2,
    AC-4.3. The owner's real test set is measured locally with the same command.
  - **Disposable Gmail account** (#96): AC-1.1 (Gmail target), AC-C.3. The Auto-Expunge check (#97) runs in the
    same session: `GMAIL_AUTO_EXPUNGE=on|off uv run pytest tests/plugins/test_gmail_setup_live.py` (with the same
    two variables set).
  - **Watchdog at-logon install on the Bridge machine** (#49): AC-P.1 (live restart within 5 minutes), AC-P.5
    (reboot).
- Not an acceptance criterion but part of shipping (§12): the Compose deploy on the tailnet host (#111).
