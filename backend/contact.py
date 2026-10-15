"""Public contact submissions and an administrator-only inbox."""
import re
import secrets
from flask import request, session, redirect, url_for, abort, jsonify
from .models import db, ContactMessage
from .api import require_user, body, integer_argument

TOPICS = ('General enquiry', 'Question correction', 'Copyright / removal', 'Privacy request')

def public_contact():
    from .study_pages import page
    from .about_api import data
    from .models import AboutPage
    token = session.setdefault('contact_csrf', secrets.token_urlsafe(32))
    values = {}
    error = None
    if request.method == 'POST':
        if not secrets.compare_digest(token, request.form.get('csrf', '')):
            abort(400, description='Refresh the Contact page and try again.')
        if request.form.get('website', '').strip():
            return redirect(url_for('study.contact', sent=1), code=303)
        values = {key: request.form.get(key, '').strip() for key in ('name', 'email', 'topic', 'message')}
        if not 1 <= len(values['name']) <= 100:
            error = 'Enter your name (up to 100 characters).'
        elif len(values['email']) > 254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', values['email']):
            error = 'Enter a valid reply email address.'
        elif values['topic'] not in TOPICS:
            error = 'Choose a topic.'
        elif not 10 <= len(values['message']) <= 5000:
            error = 'Enter a message between 10 and 5,000 characters.'
        else:
            db.session.add(ContactMessage(**values))
            db.session.commit()
            return redirect(url_for('study.contact', sent=1), code=303)
    response = page('Contact & content removal', 'Contact MauryaHub for support, corrections and copyright or content removal requests.', section='contact', about=data(db.session.get(AboutPage, 1)), contact_token=token, contact_topics=TOPICS, contact_values=values, contact_error=error, contact_sent=request.args.get('sent') == '1')
    return response, 400 if error else 200, {'Cache-Control': 'no-store'}

def register_contact_routes(admin):
    @admin.get('/contact-messages')
    @require_user(True)
    def contact_messages():
        status = request.args.get('status', 'OPEN')
        if status not in ('OPEN', 'RESOLVED', 'ALL'):
            abort(400, description='Invalid inbox status.')
        page = integer_argument('page') if 'page' in request.args else 1
        if not 1 <= page <= 100000:
            abort(400, description='Invalid inbox page.')
        query = ContactMessage.query
        if status != 'ALL':
            query = query.filter_by(status=status)
        total = query.count()
        rows = query.order_by(ContactMessage.id.desc()).offset((page - 1) * 20).limit(20).all()
        return jsonify(items=[{key: getattr(row, key) for key in ('id', 'name', 'email', 'topic', 'message', 'status', 'created_at')} for row in rows], total=total)

    @admin.patch('/contact-messages/<int:id>')
    @require_user(True)
    def update_contact_message(id):
        row = db.get_or_404(ContactMessage, id)
        status = body().get('status')
        if status not in ('OPEN', 'RESOLVED'):
            abort(400, description='Invalid inbox status.')
        row.status = status
        db.session.commit()
        return jsonify(ok=True)

    @admin.delete('/contact-messages/<int:id>')
    @require_user(True)
    def delete_contact_message(id):
        row = db.get_or_404(ContactMessage, id)
        db.session.delete(row)
        db.session.commit()
        return jsonify(ok=True)
