# Build from the repository root. Data/resources remain inside the portable folder.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

desktop = Path(SPECPATH)
base = desktop.parent
# Public build deliberately contains no historical company data.
datas = []
binaries = []
hidden = ['model_engine', 'financial_criteria', 'financial_decision_rules', 'sklearn_pipelines',
          'review_rules', 'streamlit.web.cli', 'streamlit.testing.v1', 'tkinter']
for package in ['streamlit']:
    package_data, package_bins, package_hidden = collect_all(package)
    datas += package_data
    binaries += package_bins
    hidden += package_hidden
hidden += collect_submodules('sklearn', filter=lambda name: '.tests' not in name)
for name in ['model_engine.py','financial_criteria.py','financial_decision_rules.py','sklearn_pipelines.py','industry_scope.json','docs/SCREENING_LOGIC.html']:
    datas.append((str(base/name),'payload' if not name.startswith('docs/') else 'payload/docs'))
for name in ['app.py','review_rules.py','theme.json']:
    datas.append((str(base/'application'/name),'payload/application'))
datas.append((str(base/'application/.streamlit/config.toml'),'payload/application/.streamlit'))
datas.append((str(base/'clean_data/Column_dictionary.csv'),'payload/clean_data'))
datas.append((str(base/'outputs/thai_industry_models.joblib'),'payload/outputs'))

a = Analysis([str(desktop / 'launcher.py')], pathex=[str(base), str(base / 'application')],
             binaries=binaries, datas=datas, hiddenimports=hidden,
             excludes=['matplotlib', 'notebook', 'nbconvert', 'IPython'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='ThaiCompanyReview',
          console=False, debug=False, strip=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='ThaiCompanyReview')
