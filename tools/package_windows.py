from pathlib import Path
import shutil,zipfile,hashlib,json
root=Path(__file__).resolve().parents[1];dist=root/'dist/ThaiCompanyReview'
assert (dist/'ThaiCompanyReview.exe').is_file()
shutil.copy2(root/'README.md',dist/'README.md')
shutil.copy2(root/'docs/SCREENING_LOGIC.html',dist/'SCREENING_LOGIC.html')
# Assert excluded data are not quietly copied into a public build.
for name in ['Model_input_all_items.csv','Company_coverage.csv','Company_splits.csv','Flagged_annual_characteristics.csv','All html.zip']:
 assert not list(dist.rglob(name)),name
files=[p for p in dist.rglob('*') if p.is_file()]
(dist/'Distribution_manifest.json').write_text(json.dumps({'edition':'public-reviewer','historical_company_rows_included':False,'source_evidence_included':False,'files':{p.relative_to(dist).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}},indent=2)+'\n')
with zipfile.ZipFile(root/'dist/Transfer-Pricing-Reviewer-Windows.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
 for p in sorted(dist.rglob('*')):
  if p.is_file():archive.write(p,'Transfer_Pricing_Reviewer/'+p.relative_to(dist).as_posix())
print('Built public reviewer ZIP; raw financial rows/evidence excluded.')
