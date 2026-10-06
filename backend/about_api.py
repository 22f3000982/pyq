"""Public About content with administrator-only editing."""
import io, uuid, warnings
from flask import Blueprint, jsonify, request, abort
from PIL import Image, ImageOps, UnidentifiedImageError
from .models import db, AboutPage
from .api import require_user, body
from .storage import write_asset, send_asset

about = Blueprint('about', __name__, url_prefix='/api')
DEFAULTS = {
    'headline': 'Less searching. More practising.',
    'description': 'MauryaHub PYQ Practice brings previous-year papers together so you can choose your course and start practising. Use Practice Mode to learn at your pace, or Exam Mode for a timed attempt. No student login is required.',
    'contact_email': '',
    'name': '',
    'bio': 'Built by a student, for students.',
}
LIMITS = {'headline': 160, 'description': 4000, 'name': 100, 'bio': 2000, 'contact_email': 254}

def data(row):
    return {**DEFAULTS, **(row.details if row else {}), 'photo_url': '/api/about/photo' if row and row.photo_path else None}

@about.get('/about')
def public_about():
    return jsonify(data(db.session.get(AboutPage, 1)))

@about.put('/admin/about')
@require_user(True)
def save_about():
    incoming = body()
    if set(incoming) - set(LIMITS): abort(400, description='Unknown About field.')
    for key, value in incoming.items():
        if not isinstance(value, str) or len(value) > LIMITS[key]:
            abort(400, description=f'{key} must be text, up to {LIMITS[key]} characters.')
        if key in ('headline', 'description') and not value.strip():
            abort(400, description=f'{key} cannot be empty.')
    if 'contact_email' in incoming and incoming['contact_email'].strip():
        import re
        if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", incoming['contact_email'].strip()):
            abort(400, description='Enter a valid public contact email.')
    row = db.session.get(AboutPage, 1)
    if not row:
        row = AboutPage(id=1, details={}); db.session.add(row)
    row.details = {**DEFAULTS, **row.details, **{k:v.strip() for k,v in incoming.items()}}
    db.session.commit()
    return jsonify(data(row))

@about.post('/admin/about/photo')
@require_user(True)
def upload_photo():
    upload = request.files.get('photo')
    if not upload: abort(400, description='Choose a photo.')
    raw = upload.stream.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024: abort(413, description='Photo must be 5 MB or smaller.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in ('JPEG', 'PNG', 'WEBP'): raise ValueError()
                if source.width * source.height > 20_000_000: raise ValueError()
                photo = ImageOps.exif_transpose(source)
                photo.thumbnail((800, 800))
                photo = photo.convert('RGB')
                output = io.BytesIO(); photo.save(output, format='JPEG', quality=88)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        abort(400, description='Choose a valid JPG, PNG or WebP photo (up to 20 megapixels).')
    path = 'about/' + uuid.uuid4().hex + '.jpg'
    write_asset(path, output.getvalue())
    row = db.session.get(AboutPage, 1)
    if not row:
        row = AboutPage(id=1, details=dict(DEFAULTS)); db.session.add(row)
    row.photo_path = path; db.session.commit()
    return jsonify(data(row))

@about.delete('/admin/about/photo')
@require_user(True)
def remove_photo():
    row = db.session.get(AboutPage, 1)
    if row: row.photo_path = None; db.session.commit()
    return jsonify(data(row))

@about.get('/about/photo')
def public_photo():
    row = db.session.get(AboutPage, 1)
    if not row or not row.photo_path: abort(404)
    return send_asset(row.photo_path, mimetype='image/jpeg', max_age=0)
