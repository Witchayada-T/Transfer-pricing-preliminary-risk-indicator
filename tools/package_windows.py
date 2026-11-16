from pathlib import Path
import shutil,zipfile,hashlib,json
root=Path(__file__).resolve().parents[1];dist=root/'dist/ThaiCompanyReview'
assert (dist/'ThaiCompanyReview.exe').is_file()
logic=(root/'docs/SCREENING_LOGIC.html').read_text().replace('../README.md','https://github.com/Witchayada-T/Transfer-pricing-preliminary-risk-indicator').replace('../industry_scope.json','industry_scope.json')
(dist/'SCREENING_LOGIC.html').write_text(logic)
shutil.copy2(root/'industry_scope.json',dist/'industry_scope.json')
(dist/'START_HERE.html').write_text('''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Local reviewer — start here</title><style>body{font:18px/1.65 system-ui;max-width:900px;margin:40px auto;padding:0 24px;color:#24364d}h1{color:#594779}a{color:#375d94}code{background:#edf1f7;padding:3px}</style></head><body><h1>Transfer Pricing Preliminary Risk Indicator</h1><ol><li>Extract the whole ZIP.</li><li>Double-click <strong>ThaiCompanyReview.exe</strong> in this folder.</li><li>Keep <code>_internal</code> beside the EXE.</li><li>Use the controller to open the local app and stop it when finished.</li></ol><p>No Python, AWS or online service is required. New financial inputs remain in the local application unless the reviewer explicitly exports/shares them.</p><p><a href="SCREENING_LOGIC.html">Read the screening logic offline</a> · <a href="industry_scope.json">Industry coverage metadata</a> · <a href="https://github.com/Witchayada-T/Transfer-pricing-preliminary-risk-indicator">Public source and instructions</a></p><p>This edition excludes original company observations and source evidence. A financial flag calls for review, not a tax-compliance conclusion. A documented commercial explanation may support the company’s position.</p></body></html>''')
(dist/'READ_ME_FIRST.txt').write_text('Extract the entire ZIP. Open START_HERE.html for instructions or double-click ThaiCompanyReview.exe. Keep _internal beside the EXE. Read SCREENING_LOGIC.html for the independent scoring/review rules. Original company observations and evidence archives are not included. Source: https://github.com/Witchayada-T/Transfer-pricing-preliminary-risk-indicator\n')
for name in ['Model_input_all_items.csv','Company_coverage.csv','Company_splits.csv','Flagged_annual_characteristics.csv','All html.zip']:
 assert not list(dist.rglob(name)),name
files=[p for p in dist.rglob('*') if p.is_file()]
(dist/'Distribution_manifest.json').write_text(json.dumps({'edition':'public-reviewer','historical_company_rows_included':False,'source_evidence_included':False,'files':{p.relative_to(dist).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n')
with zipfile.ZipFile(root/'dist/Transfer-Pricing-Reviewer-Windows.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
 for p in sorted(dist.rglob('*')):
  if p.is_file():archive.write(p,'Transfer_Pricing_Reviewer/'+p.relative_to(dist).as_posix())
print('Built public reviewer ZIP; raw financial rows/evidence excluded.')
