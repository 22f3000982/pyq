"""Manual ads only on editor-approved, fully solved and reviewed public paper pages."""
import re
from .site_pages import setting
from .models import db,StudyPaperSettings,ContentQualityReview
from .content_quality import fingerprint,flags

def ad_context(paper,questions,solutions):
    config=dict(enabled=False,publisher='',slot='')
    if setting('STUDY_ADS_ENABLED','false').lower()!='true':return config
    if setting('ADSENSE_CMP_READY','false').lower()!='true':return config
    publisher=setting('ADSENSE_PUBLISHER_ID');slot=setting('ADSENSE_STUDY_SLOT')
    if not re.fullmatch(r'pub-\d{16}',publisher) or not re.fullmatch(r'\d{6,20}',slot):return config
    editor=db.session.get(StudyPaperSettings,paper.id)
    if not editor or not editor.allow_ads or paper.status!='AVAILABLE' or not questions:return config
    reviews={r.question_id:r for r in ContentQualityReview.query.filter(ContentQualityReview.question_id.in_([q.id for q in questions]))}
    for q in questions:
        s=solutions.get(q.id);r=reviews.get(q.id)
        if not s or s.status!='PUBLISHED' or flags(q,s) or not r or r.fingerprint!=fingerprint(q,s):return config
    from flask import g
    g.study_ads_allowed=True
    return dict(enabled=True,publisher='ca-'+publisher,slot=slot)
