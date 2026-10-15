import re
from backend.models import db, ContactMessage
from conftest import login

def form(client):
    response = client.get('/contact')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    token = re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)
    return dict(csrf=token, name='Student', email='student@example.com', topic='Question correction', message='Please check question 2 in this paper.')

def test_contact_submission_and_private_inbox(client):
    data = form(client)
    assert client.post('/contact', data={**data, 'csrf':'wrong'}).status_code == 400
    response = client.post('/contact', data=data)
    assert response.status_code == 303
    assert ContactMessage.query.count() == 1
    assert 'Your message has been sent' in client.get(response.location).text
    assert client.get('/api/admin/contact-messages').status_code == 401
    headers = login(client, admin=True)
    response = client.get('/api/admin/contact-messages')
    assert response.json['total'] == 1
    row = response.json['items'][0]
    assert row['message'] == data['message']
    path = '/api/admin/contact-messages/' + str(row['id'])
    assert client.patch(path, json={'status':'RESOLVED'}).status_code == 403
    assert client.patch(path, json={'status':'RESOLVED'}, headers=headers).status_code == 200
    assert client.get('/api/admin/contact-messages').json['total'] == 0
    assert client.get('/api/admin/contact-messages?status=ALL').json['total'] == 1
    assert client.delete(path, headers=headers).status_code == 200
    assert ContactMessage.query.count() == 0

def test_contact_validation_spam_and_escaping(client):
    data = form(client)
    for update in ({'email':'bad'}, {'name':''}, {'topic':'bad'}, {'message':'short'}, {'message':'x'*5001}):
        assert client.post('/contact', data={**data, **update}).status_code == 400
    assert client.post('/contact', data={**data, 'website':'spam'}).status_code == 303
    assert ContactMessage.query.count() == 0
    response = client.post('/contact', data={**data, 'name':'<script>alert(1)</script>', 'message':'bad'})
    assert '<script>alert(1)</script>' not in response.text
    assert '&lt;script&gt;' in response.text

def test_contact_rate_limit(tmp_path):
    from backend import create_app, limiter
    app = create_app({'TESTING':True, 'STORAGE_BACKEND':'local', 'UPLOAD_DIR':str(tmp_path/'uploads'), 'SQLALCHEMY_DATABASE_URI':'sqlite:///'+str(tmp_path/'rate.db'), 'RATELIMIT_ENABLED':True})
    with app.app_context():
        db.create_all()
        limiter.reset()
        try:
            with app.test_client() as client:
                data = form(client)
                for _ in range(5):
                    assert client.post('/contact', data=data).status_code == 303
                assert client.post('/contact', data=data).status_code == 429
                assert client.get('/contact').status_code == 200
        finally:
            db.session.remove()
            db.drop_all()
            limiter.reset()
