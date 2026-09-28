"""Create a credential-free five-paper delivery; original database is untouched."""
import sqlite3,shutil,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];data=root/'data';data.mkdir(exist_ok=True)
ids=json.loads((root/'demo-papers.json').read_text())['paper_ids'];slots=','.join('?' for _ in ids)
with sqlite3.connect(root/'instance/app.db') as src,sqlite3.connect(data/'initial.sqlite3') as dst:src.backup(dst)
con=sqlite3.connect(data/'initial.sqlite3');con.execute('PRAGMA foreign_keys=OFF')
for table in ['attempt_answer','attempt','bookmark','question_review']:con.execute(f'DELETE FROM {table}')
con.execute('DROP TABLE IF EXISTS _alembic_tmp_ingestion_batch')
removed=f"select id from question where paper_id not in ({slots}) or status='SUPERSEDED'"
for table in ['question_option','question_image']:con.execute(f'DELETE FROM {table} WHERE question_id in ({removed})',ids)
con.execute(f"DELETE FROM question WHERE paper_id not in ({slots}) or status='SUPERSEDED'",ids)
con.execute(f'DELETE FROM ingestion_file WHERE paper_id not in ({slots})',ids)
con.execute("DELETE FROM ingestion_batch WHERE id not in (select batch_id from ingestion_file)")
con.execute(f"UPDATE paper SET status='CATALOG_ONLY',source_metadata='{{}}',duration_seconds=NULL,canonical_paper_id=NULL WHERE id not in ({slots})",ids)
con.execute('DELETE FROM user')
con.execute("INSERT INTO user(id,email,name,password_hash,role,active,created_at) VALUES(1,'ingestion-service@internal.invalid','Ingestion service','!disabled','SYSTEM',0,0)")
con.execute('UPDATE ingestion_batch SET user_id=1');con.execute("UPDATE ingestion_batch SET status='COMPLETED'");con.commit()
refs={r[0] for r in con.execute('select path from ingestion_file where path is not null')}|{r[0] for r in con.execute('select path from question_image')}
assets=data/'assets'
if assets.exists():shutil.rmtree(assets)
assets.mkdir()
for name in refs:
    source=root/'uploads'/name
    if not source.exists():raise RuntimeError('Missing source asset '+name)
    shutil.copy2(source,assets/name)
issues=con.execute('PRAGMA foreign_key_check').fetchall();assert not issues,issues
assert con.execute("select count(*) from question where status='AVAILABLE'").fetchone()[0]==111
assert con.execute("select count(*) from ingestion_file where status in ('QUEUED','FETCH_QUEUED','PROCESSING','FETCHING')").fetchone()[0]==0
print('Snapshot:',len(ids),'papers, 111 student questions,',len(refs),'assets; foreign keys valid; no active jobs; no login credentials.')
con.execute('VACUUM');con.close()
