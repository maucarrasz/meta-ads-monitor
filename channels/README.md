# Channel detector using owner Google project

Runs daily at 07:02 America/Lima (12:02 UTC) and on manual dispatch. GitHub schedules may be delayed.

This first stage reads the three channel tabs from their existing private workbook, resolves public YouTube channel feeds, writes last successful check and private baseline/detection rows to hidden BASE_CANALES_WIF in that same workbook. First successful observation per channel is a baseline, not news. Later new feed entries are PENDIENTE. Existing downstream transcript, curation and store-spy workflows are not replaced or marked complete.

No JSON service-account key, no Cloud Run, no paid API. The existing WIF service account uses only Sheets scope. Source records and video content never enter logs, summaries, commits or artifacts. Standard public-repository runner; logs contain counts only. Do not add debug dumps or persist the generated authentication file. Unknown providers, unresolvable channels or rate limits are reported as failures; no login or bypass is attempted. Failed channel checks do not advance last successful check.

RSS is a bounded recent feed, not a historical archive. Existing baseline migration and downstream handoff must be reconciled before retiring current channel monitors.
