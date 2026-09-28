"""Read-only Cloudflare R2 connectivity and authentication check.

This command never converts credentials, edits .env, uploads, overwrites, or
deletes objects. It performs only ListObjectsV2(MaxKeys=1) on each configured
bucket through the existing storage configuration.
"""
import os, secrets, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

os.environ.setdefault('SECRET_KEY', secrets.token_hex(32))

from backend import create_app
from backend.storage import StorageError, check_access, configured


def main():
    app = create_app({'STORAGE_BACKEND': 'r2'})
    if not configured(app.config) or not (app.config.get('R2_PDF_BUCKET_NAME') and app.config.get('R2_IMAGE_BUCKET_NAME')):
        print('R2 BLOCKED: endpoint, access key, secret, and separate PDF/image bucket names are required.')
        return 2
    try:
        with app.app_context():
            check_access()
        print('R2 PASS: authenticated read-only access to configured bucket(s) succeeded.')
        return 0
    except StorageError as exc:
        print('R2 BLOCKED: ' + str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
