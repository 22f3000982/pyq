from xml.etree.ElementTree import fromstring
from test_study_pages import seed
from backend.models import db

def test_policy_contact_and_real_not_found(app,client):
    for url in ['/privacy','/content-policy','/contact']:
        r=client.get(url);assert r.status_code==200
        assert 'ashraj77777@gmail.com' in r.text
        assert 'officially authorised' not in r.text.lower()
    assert 'IITM BS Degree student' in client.get('/content-policy').text
    r=client.get('/does-not-exist');assert r.status_code==404 and 'Page not found' in r.text
    assert client.get('/api/does-not-exist').status_code==404

def test_crawl_and_verification_configuration(app,client):
    c,p,q,s=seed()
    app.config.update(PUBLIC_SITE_URL='https://mauryahub.in',GOOGLE_SITE_VERIFICATION='token"escaped',ADSENSE_PUBLISHER_ID='pub-1234567890123456')
    r=client.get('/robots.txt');assert r.mimetype=='text/plain' and 'Sitemap: https://mauryahub.in/sitemap.xml' in r.text
    r=client.get('/sitemap.xml');assert r.mimetype=='application/xml';fromstring(r.data)
    assert f'/study/papers/{p.id}' in r.text and f'/study/courses/{c.id}' in r.text
    assert '/attempt/' not in r.text
    page=client.get('/study?q=maths').text
    assert 'href="https://mauryahub.in/study"' in page
    assert 'token&#34;escaped' in page and 'ca-pub-1234567890123456' in page
    r=client.get('/ads.txt');assert r.mimetype=='text/plain' and r.text=='google.com, pub-1234567890123456, DIRECT, f08c47fec0942fa0\n'
    p.status='ARCHIVED';db.session.commit();assert f'/study/papers/{p.id}' not in client.get('/sitemap.xml').text
    app.config['ADSENSE_PUBLISHER_ID']='invalid';r=client.get('/ads.txt');assert r.status_code==404 and r.mimetype=='text/plain'
    assert 'google-adsense-account' not in client.get('/study').text

def test_spa_canonical_and_private_routes(app,client):
    app.config.update(GOOGLE_SITE_VERIFICATION='verify-token',ADSENSE_PUBLISHER_ID='')
    r=client.get('/');assert 'rel="canonical" href="https://mauryahub.in/"' in r.text and 'verify-token' in r.text
    assert client.get('/admin/login').headers['X-Robots-Tag']=='noindex, nofollow'


def test_home_rendering_resources_are_not_blocked(client):
    # Google's longest matching rule wins; $ anchors exact public endpoints.
    rules=[]
    for line in client.get('/robots.txt').text.splitlines():
        if line.startswith(('Allow:', 'Disallow:')):
            key,path=line.split(':',1);rules.append((key,path.strip()))
    def allowed(path):
        matches=[(len(rule.rstrip('$')),kind=='Allow') for kind,rule in rules if (path==rule[:-1] if rule.endswith('$') else path.startswith(rule))]
        return max(matches)[1] if matches else True
    for path in ('/','/assets/app-any.js','/study','/api/home','/api/session','/api/study-featured'):
        assert allowed(path),path
    for path in ('/api/admin/stats','/api/attempts/1','/api/auth/login','/api/session/extra'):
        assert not allowed(path),path
    assert client.get('/api/session').headers['X-Robots-Tag']=='noindex'
    assert client.get('/api/session').headers['Cache-Control']=='no-store'
