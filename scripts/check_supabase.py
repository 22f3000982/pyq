"""Read-only Supabase connection check using the existing Flask/SQLAlchemy setup."""
import os,secrets,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env')
if not os.getenv('DATABASE_URL','').startswith(('postgresql://','postgresql+psycopg://','postgres://')):
    raise SystemExit('Set a PostgreSQL DATABASE_URL privately in the environment or .env. No database was contacted.')
os.environ.setdefault('SECRET_KEY',secrets.token_hex(32))
try:
    from backend import create_app
    app=create_app()
    result=app.test_cli_runner().invoke(args=['check-db'])
    print(result.output,end='')
    raise SystemExit(result.exit_code)
except SystemExit:raise
except Exception:
    raise SystemExit('Could not initialize the connection check. Check dependencies and DATABASE_URL privately. No migrations were run.') from None
