"""Public policy, crawl and verification endpoints; no student sessions."""
import os,re
from urllib.parse import urlsplit
from xml.etree.ElementTree import Element,SubElement,tostring
from flask import Blueprint,current_app,request,Response,render_template
from .models import db,Paper,Question,AboutPage
from .about_api import data
site=Blueprint('site',__name__)
def setting(key,default=''):
    return str(current_app.config.get(key,os.getenv(key,default))).strip()
def origin():
    value=setting('PUBLIC_SITE_URL','https://mauryahub.in').rstrip('/')
    parsed=urlsplit(value)
    if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.query or parsed.fragment or parsed.path or parsed.username:
        raise ValueError('PUBLIC_SITE_URL must be an HTTP(S) origin without a path.')
    return value

def metadata():
    publisher=setting('ADSENSE_PUBLISHER_ID')
    publisher=publisher if re.fullmatch(r'pub-\d{16}',publisher) else ''
    return dict(canonical_url=origin()+request.path,site_verification=setting('GOOGLE_SITE_VERIFICATION'),adsense_account='ca-'+publisher if publisher else '')
@site.get('/robots.txt')
def robots():
    return Response('User-agent: *\nAllow: /\nDisallow: /api/\nSitemap: '+origin()+'/sitemap.xml\n',mimetype='text/plain',headers={'Cache-Control':'public, max-age=300'})
@site.get('/sitemap.xml')
def sitemap():
    ready=db.session.query(Question.paper_id).filter(Question.status=='AVAILABLE')
    rows=db.session.query(Paper.id,Paper.course_id).filter(Paper.status!='ARCHIVED',Paper.id.in_(ready)).all()
    paths=['/','/study','/about','/contact','/privacy','/content-policy']
    paths += [f'/study/courses/{i}' for i in sorted({r.course_id for r in rows})]
    paths += [f'/study/papers/{r.id}' for r in rows]
    root=Element('urlset',xmlns='http://www.sitemaps.org/schemas/sitemap/0.9')
    for path in paths:SubElement(SubElement(root,'url'),'loc').text=origin()+path
    return Response(tostring(root,encoding='utf-8',xml_declaration=True),mimetype='application/xml',headers={'Cache-Control':'public, max-age=300'})
@site.get('/ads.txt')
def ads():
    publisher=setting('ADSENSE_PUBLISHER_ID')
    if not re.fullmatch(r'pub-\d{16}',publisher):
        return Response('# No advertising seller configured.\n',status=404,mimetype='text/plain')
    return Response(f'google.com, {publisher}, DIRECT, f08c47fec0942fa0\n',mimetype='text/plain',headers={'Cache-Control':'public, max-age=300'})
@site.get('/privacy')
@site.get('/content-policy')
def policy():
    from .study_pages import page
    section='privacy' if request.path=='/privacy' else 'content_policy'
    return page('Privacy Policy' if section=='privacy' else 'Content & corrections policy','How MauryaHub handles site data.' if section=='privacy' else 'Content ownership, educational use and corrections at MauryaHub.',section=section,about=data(db.session.get(AboutPage,1)))
