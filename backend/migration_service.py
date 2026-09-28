"""Explicit migration helpers; never invoked by normal application startup."""
import hashlib,json,os,re,sqlite3
from pathlib import Path
from urllib.parse import quote,quote_plus
from sqlalchemy import create_engine,select,text,inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url
from .models import db
from .database_config import database_url,engine_options

DISPOSABLE_MIGRATION_TABLES={'user','attempt','attempt_answer','paper_progress','bookmark','question_review'}


def digest_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def backup_sqlite(source,destination):
    source=Path(source).resolve();destination=Path(destination).resolve()
    if not source.is_file():raise ValueError('Source SQLite database does not exist')
    if destination.exists() or destination==source:raise ValueError('Backup destination must be a new file')
    destination.parent.mkdir(parents=True,exist_ok=True)
    before=digest_file(source)
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(destination) as dst:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite backup integrity_check failed')
        if dst.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('SQLite backup contains broken foreign keys')
    if digest_file(source)!=before:raise RuntimeError('Source changed during backup; stop the local app and retry')
    return before


def target_identity(uri):
    u=make_url(uri)
    value=json.dumps([u.get_backend_name(),u.host,u.port,u.database,u.username])
    return hashlib.sha256(value.encode()).hexdigest()


def redact(value,secrets=()):
    result=str(value)
    for secret in sorted({s for s in secrets if s},key=len,reverse=True):
        for form in {secret,quote(secret,safe=''),quote_plus(secret)}:result=result.replace(form,'[REDACTED]')
    return re.sub(r'postgres(?:ql)?(?:\+\w+)?://[^\s\"\'<>]+','[DATABASE_URL REDACTED]',result)


def safe_error(exc,secrets=()):
    original=getattr(exc,'orig',exc);diag=getattr(original,'diag',None)
    message=getattr(diag,'message_primary',None) or str(original)
    # SQLAlchemy exception __str__ can contain whole rows/password hashes; use
    # the driver's primary diagnostic instead of SQL/parameters when available.
    state=getattr(original,'sqlstate',None)
    return {'type':type(original).__name__,'sqlstate':state,'message':redact(message,secrets)}


def read_only_check(engine):
    with engine.connect() as conn:
        if conn.dialect.name!='postgresql':raise ValueError('Destination must be PostgreSQL')
        conn.execute(text('SET TRANSACTION READ ONLY'))
        if conn.execute(text('SELECT 1')).scalar_one()!=1:raise RuntimeError('SELECT 1 failed')
        conn.rollback()


def assert_empty_target(engine):
    """Reuse a complete empty schema; never overwrite rows or partial schemas."""
    inspector=inspect(engine)
    schema='public' if engine.dialect.name=='postgresql' else None
    existing=set(inspector.get_table_names(schema=schema))
    required=set(db.metadata.tables)
    found=existing & (required|{'alembic_version'})
    if not found:return False
    if not required.issubset(existing) or 'alembic_version' not in existing:
        raise RuntimeError('Destination has a partial application schema. Nothing was overwritten.')
    with engine.connect() as conn:
        versions=conn.execute(text('SELECT version_num FROM alembic_version')).scalars().all()
        if versions!=['d41e7c120001']:
            raise RuntimeError('Existing schema revision does not match this release. Nothing was overwritten.')
        for table in db.metadata.sorted_tables:
            if conn.execute(select(table).limit(1)).first() is not None:
                raise RuntimeError('Destination contains data in '+table.name+'; refusing to overwrite.')
            actual={c['name']:c for c in inspector.get_columns(table.name,schema=schema)}
            if set(actual)!=set(table.c.keys()):
                raise RuntimeError('Column mismatch in '+table.name)
            for col in table.c:
                if actual[col.name]['type']._type_affinity is not col.type._type_affinity:
                    raise RuntimeError('Column type mismatch in '+table.name+'.'+col.name)
                if bool(actual[col.name]['nullable'])!=bool(col.nullable):
                    raise RuntimeError('Column nullability mismatch in '+table.name+'.'+col.name)
            pk=inspector.get_pk_constraint(table.name,schema=schema)['constrained_columns']
            if pk!=list(table.primary_key.columns.keys()):raise RuntimeError('Primary key mismatch in '+table.name)
            expected_fk={(tuple(f.parent.name for f in c.elements),c.referred_table.name,tuple(f.column.name for f in c.elements)) for c in table.foreign_key_constraints}
            actual_fk={(tuple(c['constrained_columns']),c['referred_table'],tuple(c['referred_columns'])) for c in inspector.get_foreign_keys(table.name,schema=schema)}
            if expected_fk!=actual_fk:raise RuntimeError('Foreign key mismatch in '+table.name)
            from sqlalchemy import UniqueConstraint
            expected_unique={tuple(c.columns.keys()) for c in table.constraints if isinstance(c,UniqueConstraint)}
            actual_unique={tuple(c['column_names']) for c in inspector.get_unique_constraints(table.name,schema=schema)}
            if not expected_unique.issubset(actual_unique):raise RuntimeError('Unique constraint mismatch in '+table.name)
    return True


def validate_source(source,uploads):
    """Reject the empty installation that previously produced an empty import."""
    with sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True) as conn:
        counts={name:conn.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0] for name in ('paper','question','user')}
        if not counts['paper'] or not counts['question']:
            raise RuntimeError('Source SQLite has no paper/question data. Select the populated Final-App folder.')
        images=[row[0] for row in conn.execute('SELECT path FROM question_image')]
    root=Path(uploads).resolve()
    for name in images:
        path=(root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise RuntimeError('A required question image is missing from uploads; source assets must accompany the database.')
    return counts


def table_digest(connection,table):
    # A pooler/server can inherit extra_float_digits=0, which rounds FLOAT
    # timestamps on text transfer. Ask PostgreSQL for lossless output within
    # this transaction; never round or loosen the integrity comparison.
    if connection.dialect.name=='postgresql':
        connection.execute(text('SET LOCAL extra_float_digits = 3'))
    h=hashlib.sha256();count=0
    rows=connection.execute(select(table).order_by(*table.primary_key.columns)).mappings()
    for row in rows:
        h.update(json.dumps(dict(row),sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str).encode());h.update(b'\n');count+=1
    return {'rows':count,'sha256':h.hexdigest()}


def copy_and_verify(source_engine,target_engine):
    """Rows imported atomically; preserve IDs, JSON, passwords and relationships."""
    report={}
    with source_engine.connect() as source,target_engine.begin() as target:
        for table in db.metadata.sorted_tables:
            deferred=[]
            self_cols=[c for c in table.columns if any(f.column.table.name==table.name for f in c.foreign_keys)]
            rows=source.execute(select(table).order_by(*table.primary_key.columns)).mappings()
            batch=[]
            for row in rows:
                values=dict(row)
                refs={c.name:values[c.name] for c in self_cols if values[c.name] is not None}
                if refs:
                    deferred.append((values['id'],refs))
                    for name in refs:values[name]=None
                batch.append(values)
                if len(batch)>=250:target.execute(table.insert(),batch);batch=[]
            if batch:target.execute(table.insert(),batch)
            for identity,refs in deferred:target.execute(table.update().where(table.c.id==identity).values(**refs))
            expected=table_digest(source,table);actual=table_digest(target,table)
            if actual!=expected:raise RuntimeError('Row count/content digest mismatch in '+table.name)
            report[table.name]=actual
            if target.dialect.name=='postgresql' and 'id' in table.c and table.c.id.primary_key:
                quoted=target.dialect.identifier_preparer.quote(table.name)
                target.execute(text(f"SELECT setval(pg_get_serial_sequence(:name,'id'),COALESCE((SELECT MAX(id) FROM {quoted}),1),(SELECT COUNT(*)>0 FROM {quoted}))"),{'name':quoted})
        # PostgreSQL constraints are immediate; force a final check if any deferred
        # constraints are introduced in a future migration.
        if target.dialect.name=='postgresql':target.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
    return report


def reconcile_stable_rows(source_engine,target_engine):
    """Insert missing stable rows, preserve destination-only rows, and refuse conflicts."""
    report={'tables':{},'conflicts':[]}
    with source_engine.connect() as source,target_engine.begin() as target:
        for table in db.metadata.sorted_tables:
            primary=list(table.primary_key.columns)
            if not primary:continue
            inserted=existing=0;deferred=[]
            for row in source.execute(select(table).order_by(*primary)).mappings():
                values=dict(row);where=[c==values[c.name] for c in primary]
                found=target.execute(select(table).where(*where)).mappings().first()
                if found is not None:
                    if dict(found)!=values:
                        conflict={'table':table.name,'key':{c.name:values[c.name] for c in primary}}
                        report['conflicts'].append(conflict)
                        raise RuntimeError('Stable record conflict in '+table.name+' for primary key '+json.dumps(conflict['key'],default=str))
                    existing+=1;continue
                self_cols=[c for c in table.columns if any(f.column.table.name==table.name for f in c.foreign_keys)]
                refs={c.name:values[c.name] for c in self_cols if values[c.name] is not None}
                if refs:
                    deferred.append((table,{c.name:values[c.name] for c in primary},refs))
                    for name in refs:values[name]=None
                try:target.execute(table.insert(),values)
                except IntegrityError:
                    raise RuntimeError('Stable record conflicts in '+table.name+' (primary key or unique identity); no destination rows were overwritten.') from None
                inserted+=1
            for same_table,key,refs in deferred:
                same_primary=list(same_table.primary_key.columns)
                target.execute(same_table.update().where(*[c==key[c.name] for c in same_primary]).values(**refs))
            report['tables'][table.name]={'source_rows':inserted+existing,'inserted':inserted,'existing':existing}
        if report['conflicts']:raise RuntimeError('Stable record conflicts detected; no destination rows were overwritten.')
    return report


def verify_source_rows(source_engine,target_engine):
    """Verify every source row exists unchanged while allowing destination-only data."""
    with source_engine.connect() as source,target_engine.connect() as target:
        for table in db.metadata.sorted_tables:
            primary=list(table.primary_key.columns)
            for row in source.execute(select(table).order_by(*primary)).mappings():
                where=[c==row[c.name] for c in primary]
                found=target.execute(select(table).where(*where)).mappings().first()
                if found is None or dict(found)!=dict(row):
                    raise RuntimeError('Post-migration stable row verification failed in '+table.name)
    return True


def protect_backend_tables(engine):
    # Flask connects as the table owner. Supabase anon/authenticated Data API
    # clients must not bypass Flask's answer-key and per-user checks.
    with engine.begin() as conn:
        for name in db.metadata.tables:
            quoted=conn.dialect.identifier_preparer.quote(name)
            conn.execute(text(f'ALTER TABLE {quoted} ENABLE ROW LEVEL SECURITY'))


def verify_import(source_engine,target_engine):
    report={}
    with source_engine.connect() as source,target_engine.connect() as target:
        for table in db.metadata.sorted_tables:
            expected=table_digest(source,table);actual=table_digest(target,table)
            if actual!=expected:raise RuntimeError('Post-test data integrity mismatch in '+table.name)
            report[table.name]=actual
    return report


def confirmed_fixture_accounts(rows):
    """Require exact fixture identity AND its generated password hash to match."""
    from werkzeug.security import check_password_hash
    expected={'admin@example.test':('Admin','ADMIN'),'student@example.test':('Student','STUDENT')}
    if not rows or len(rows)>2:return False
    for row in rows:
        if expected.get(row['email'])!=(row['name'],row['role']):return False
        try:
            if not check_password_hash(row['password_hash'],'test-password-123'):return False
        except (TypeError,ValueError):return False
    return len({row['email'] for row in rows})==len(rows)


def archive_confirmed_fixture_accounts(engine):
    """Recover only the old tests' exact accounts; never erase real user data.

    All other app tables must be empty. Archive and removal are one transaction.
    Unknown users, populated tables or schema problems cause NO changes.
    """
    from sqlalchemy import MetaData
    import uuid
    with engine.begin() as conn:
        if conn.dialect.name!='postgresql':raise ValueError('Recovery requires PostgreSQL')
        required=set(db.metadata.tables)
        existing=set(inspect(conn).get_table_names(schema='public'))
        if not (required|{'alembic_version'}).issubset(existing):return None
        if conn.execute(text('SELECT version_num FROM public.alembic_version')).scalars().all()!=['d41e7c120001']:return None
        conn.execute(text("SET LOCAL lock_timeout='10s'"))
        quote_name=conn.dialect.identifier_preparer.quote
        names=', '.join('public.'+quote_name(n) for n in sorted(required))
        conn.execute(text('LOCK TABLE '+names+' IN ACCESS EXCLUSIVE MODE'))
        meta=MetaData()
        user=db.metadata.tables['user'].to_metadata(meta,schema='public')
        rows=[dict(row) for row in conn.execute(select(user)).mappings()]
        if not rows:return None
        # A nonempty question bank must never be interpreted as test residue.
        for table in db.metadata.sorted_tables:
            if table.name=='user':continue
            public_table=table.to_metadata(meta,schema='public')
            if conn.execute(select(public_table).limit(1)).first():return None
        if not confirmed_fixture_accounts(rows):return None
        schema='pyq_recovery_'+uuid.uuid4().hex
        conn.execute(text('CREATE SCHEMA '+quote_name(schema)))
        archived=user.to_metadata(MetaData(),schema=schema)
        archived.create(conn)
        full=quote_name(schema)+'.'+quote_name('user')
        conn.execute(text('ALTER TABLE '+full+' ENABLE ROW LEVEL SECURITY'))
        conn.execute(text('REVOKE ALL ON SCHEMA '+quote_name(schema)+' FROM PUBLIC, anon, authenticated'))
        conn.execute(text('REVOKE ALL ON TABLE '+full+' FROM PUBLIC, anon, authenticated'))
        conn.execute(archived.insert(),rows)
        expected=table_digest(conn,user);saved=table_digest(conn,archived)
        if expected!=saved:raise RuntimeError('Test-account archive integrity mismatch; no changes committed.')
        conn.execute(user.delete().where(user.c.id.in_([row['id'] for row in rows])))
        return {'count':len(rows),'backup_schema':schema,'sha256':saved['sha256']}


def sqlite_logical_contents(path,exclude=None):
    """Read all user tables without changing SQLite; ignore physical page layout."""
    path=Path(path).resolve()
    if not path.is_file():raise RuntimeError('Checkpoint database file is missing.')
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as conn:
        conn.execute('BEGIN')
        names=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        result={}
        excluded=set(exclude or ())
        for name in names:
            if name in excluded:continue
            quoted='"'+name.replace('"','""')+'"'
            columns=conn.execute('PRAGMA table_info('+quoted+')').fetchall()
            primary=[r[1] for r in sorted(columns,key=lambda r:r[5]) if r[5]]
            order=primary or [r[1] for r in columns]
            ordering=','.join('"'+n.replace('"','""')+'"' for n in order)
            digest=hashlib.sha256();count=0
            for row in conn.execute('SELECT * FROM '+quoted+' ORDER BY '+ordering):
                digest.update(json.dumps(row,ensure_ascii=False,separators=(',',':'),default=str).encode());digest.update(b'\n');count+=1
            result[name]={'columns':columns,'rows':count,'sha256':digest.hexdigest()}
        return result


def prepare_stable_migration_snapshot(path):
    """Remove development sessions from a disposable SQLite working copy.

    Stable catalog/content and ingestion rows remain. A disabled synthetic
    ingestion owner is used only when ingestion batches need their required
    user foreign key; no development user or password is copied.
    """
    path=Path(path).resolve()
    with sqlite3.connect(path) as conn:
        conn.execute('PRAGMA foreign_keys=ON')
        tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in ('question_review','bookmark','paper_progress','attempt_answer','attempt'):
            if table in tables:conn.execute('DELETE FROM "'+table+'"')
        if 'user' in tables:
            batches=conn.execute('SELECT COUNT(*) FROM ingestion_batch').fetchone()[0] if 'ingestion_batch' in tables else 0
            if batches:
                synthetic_id=(conn.execute('SELECT COALESCE(MAX(id),0)+1 FROM "user"').fetchone()[0])
                conn.execute('INSERT INTO "user" (id,email,name,password_hash,role,active,created_at) VALUES (?,?,?,?,?,?,?)',(synthetic_id,'ingestion-migration-'+str(synthetic_id)+'@internal.invalid','Ingestion service','!migration-system-account-disabled!','SYSTEM',0,0))
                conn.execute('UPDATE ingestion_batch SET user_id=?',(synthetic_id,))
                conn.execute('DELETE FROM "user" WHERE id<>?',(synthetic_id,))
            else:conn.execute('DELETE FROM "user"')
        conn.commit()
    return {'excluded_tables':sorted(DISPOSABLE_MIGRATION_TABLES),'system_user_created':bool(batches) if 'user' in tables else False}


def verified_resume_snapshot(root,original_hash,target_uri,target_engine,original_source=None,diagnostics=None):
    """Resume only after logical stable-record and remote-content validation.

    The physical SQLite file hash is retained only for legacy callers that do
    not provide a source database. The production migration path always uses
    stable table contents, so disposable development activity is not a gate.
    """
    details=diagnostics if diagnostics is not None else {}
    details['candidates']=[];current_contents=None;changed_tables=set();missing=[]
    for path in sorted(Path(root).glob('migration-backups/*/report.json'),reverse=True):
        try:report=json.loads(path.read_text(encoding='utf-8'))
        except (OSError,ValueError):continue
        if not report.get('tables') or report.get('target_identity')!=target_identity(target_uri):continue
        info={'checkpoint':path.parent.name};details['candidates'].append(info)
        snapshot=path.parent/'working.sqlite3'
        if not snapshot.is_file():
            info['reason']='working.sqlite3 missing';missing.append(path.parent.name);continue
        if original_source is not None:
            previous=path.parent/'original.sqlite3'
            if not previous.is_file():
                info['reason']='original.sqlite3 missing';missing.append(path.parent.name);continue
            if current_contents is None:current_contents=sqlite_logical_contents(original_source,DISPOSABLE_MIGRATION_TABLES)
            prior_contents=sqlite_logical_contents(previous,DISPOSABLE_MIGRATION_TABLES)
            differences=sorted(name for name in set(current_contents)|set(prior_contents) if current_contents.get(name)!=prior_contents.get(name))
            if differences:
                info['reason']='local table contents changed';info['changed_tables']=differences
                changed_tables.update(differences);continue
            info['source_match']='logical_stable_contents'
        elif report.get('original_sha256')==original_hash:
            info['source_match']='legacy_file_hash'
        else:
            info['reason']='file hash changed; source backup needed for logical comparison';continue
        source=create_engine('sqlite://',creator=lambda p=snapshot.resolve():sqlite3.connect(p.as_uri()+'?mode=ro',uri=True))
        try:
            with source.connect() as conn:
                recorded={t.name:table_digest(conn,t) for t in db.metadata.sorted_tables}
            if recorded!=report['tables']:
                raise RuntimeError('Saved working snapshot differs from its recorded import digests. Resume blocked; no rows overwritten.')
            try:verify_import(source,target_engine)
            except Exception:
                raise RuntimeError('Previous import differs from its saved snapshot. Resume blocked; no rows overwritten.') from None
        finally:source.dispose()
        info['remote_match']='exact_table_contents';details['selected_checkpoint']=path.parent.name
        return snapshot
    if changed_tables:
        details['changed_tables']=sorted(changed_tables)
        raise RuntimeError('Local SQLite records or schema changed since the previous import in: '+', '.join(sorted(changed_tables))+'. Both versions are preserved. Resume stopped to avoid losing newer local data; see resume_check in report.json.')
    if missing:
        raise RuntimeError('Previous import checkpoint files are missing in: '+', '.join(missing)+'. Keep the original migration-backups folder. No rows overwritten.')
    return None


def npm_command():
    """Run npm through node directly on Windows, avoiding .cmd exit-code quirks."""
    import shutil
    node=shutil.which('node');npm=shutil.which('npm.cmd' if os.name=='nt' else 'npm')
    if not node or not npm:raise RuntimeError('Node.js and npm must be installed for frontend tests.')
    base=Path(npm).resolve().parent
    choices=[base/'node_modules/npm/bin/npm-cli.js',Path(node).resolve().parent/'node_modules/npm/bin/npm-cli.js']
    for path in choices:
        if path.is_file():return [node,str(path)]
    if Path(npm).resolve().name=='npm-cli.js':return [node,str(Path(npm).resolve())]
    return [npm]
