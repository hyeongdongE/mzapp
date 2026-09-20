# Evaluation guide

The canonical metric definitions, zero-denominator policy, daily/weekly commands, and observed PoC
results are maintained in [evaluation.md](evaluation.md). The next-decision rule currently returns
`CONTINUE_DATA_COLLECTION`; fewer than 14 complete Google Trends + Wikimedia collection days can
never justify `READY_FOR_USER_MVP`.
