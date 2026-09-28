"""Run after stopping the app. Back up SQLite, then repair only downloaded papers."""
import sys,json,sqlite3,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import create_app
from backend.models import db
from backend.layout_repair import repair_layouts
app=create_app()
with app.app_context():
    if db.engine.url.get_backend_name()!='sqlite':raise SystemExit('Automatic repair requires SQLite backup; code installed but data not changed.')
    folder=ROOT/'update-backups';folder.mkdir(exist_ok=True)
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup=folder/('before-layout-v3-'+stamp+'.sqlite3')
    with sqlite3.connect(db.engine.url.database) as source,sqlite3.connect(backup) as dest:source.backup(dest)
    print('Database backup:',backup,flush=True)
    report=repair_layouts()
    output=folder/('layout-v3-report-'+stamp+'.json');output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    for row in report:print(f"Paper {row['paper_id']}: {row['status']}; {row['updated']} questions repaired; {len(row['skipped'])} unchanged",flush=True)
    print('Detailed report:',output)
    if any(r['status']!='COMPLETED' for r in report):raise SystemExit('Some source layouts could not be safely repaired. See the report; other papers completed.')
    print('Layout repair complete. Accounts, grading, responses and scores preserved. No catalog downloads started.')
