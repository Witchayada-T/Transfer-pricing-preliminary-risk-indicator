# Verification

The public reviewer is checked without loading or publishing historical company rows.

- The rule-engine tests check Yes/No/Unknown handling and the independent concern result.
- The smoke test loads the frozen model, renders the app, checks supported/unsupported inputs and confirms that the historical example browser and exploration page are absent.
- Windows CI tests the packaged executable, loopback server and desktop controller before publishing a ZIP.
- `Linux_reviewer_smoke.json` is a source-runtime receipt. Windows receipts are included with each successful standalone build.

Synthetic inputs in smoke tests are test fixtures, not company observations or evidence of TP prediction accuracy.
