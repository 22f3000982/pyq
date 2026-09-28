"""Initialize a fresh installation from the delivered, sanitized question-bank snapshot."""
from pathlib import Path
import secrets,shutil,sqlite3
ROOT=Path(__file__).resolve().parents[1]
if not (ROOT/'.env').exists():(ROOT/'.env').write_text('SECRET_KEY='+secrets.token_hex(32)+'\n')
(ROOT/'instance').mkdir(exist_ok=True)
source=ROOT/'data/initial.sqlite3';target=ROOT/'instance/app.db'
if target.exists():print('Existing database preserved. Run flask db upgrade for schema updates.')
elif source.exists():
    with sqlite3.connect(source) as src,sqlite3.connect(target) as dst:src.backup(dst)
    print('Initialized from the processed catalog and structured question bank.')
else:print('No snapshot included. Run flask db upgrade, then flask populate sample-data/catalog.xlsx.')
(ROOT/'uploads').mkdir(exist_ok=True)
assets=ROOT/'data/assets'
if assets.exists():
    for p in assets.iterdir():
        if p.is_file() and not (ROOT/'uploads'/p.name).exists():shutil.copy2(p,ROOT/'uploads'/p.name)
print('Create your admin securely: python -m flask --app backend:create_app create-admin')
print('Start the app and upload worker: python scripts/run_local.py')
