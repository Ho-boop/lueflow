# AI-assisted development workflow

The author independently owns requirement decisions, integration, and acceptance. AI is used for implementation assistance and debugging.

1. Express the instrument format, expected units, and formulas as module contracts.
2. Split parsing, curve interpolation, numerical integration, reporting, and desktop interactions.
3. Review generated code against failure cases: peak-table rows, absorbance conventions, and leading empty tab fields.
4. Check scientific results using constant-spectrum analytic answers, physical bounds, and the Jsc/Voc/FF/PCE identity.
5. Preserve regression fixtures and inspect exported reports/tables before accepting a change.

This portfolio release adds a portable CLI, removes import-time dependency installation, fixes the table tool's tab alignment, and replaces private-data-dependent tests with synthetic cases. Public fixture output is a software verification example, not an experimental result.
