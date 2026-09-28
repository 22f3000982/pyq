import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import create_app
from backend.acquisition import queue_catalog,download_pending
app=create_app()
with app.app_context():print('Batch/new jobs:',queue_catalog(retry='--retry' in sys.argv),flush=True)
download_pending(app,workers=8)
