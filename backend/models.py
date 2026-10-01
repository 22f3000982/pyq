"""Portable relational schema. JSON carries extensible question content/snapshots."""
import time
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()
@event.listens_for(Engine, 'connect')
def sqlite_foreign_keys(connection, _):
    if connection.__class__.__module__.startswith('sqlite3'):
        connection.execute('PRAGMA foreign_keys=ON')

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(12), default='STUDENT', nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.Float, default=time.time)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    code = db.Column(db.String(40), unique=True)
    level = db.Column(db.String(40))
    course_type = db.Column(db.String(40))
    aliases = db.Column(db.JSON, default=list)

class Term(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    year = db.Column(db.Integer, nullable=False, index=True)
    month = db.Column(db.Integer, nullable=False)

class ExamType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)

class Paper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    identity = db.Column(db.String(64), unique=True, nullable=False)
    course_id = db.Column(db.ForeignKey('course.id'), nullable=False, index=True)
    term_id = db.Column(db.ForeignKey('term.id'), nullable=False, index=True)
    exam_type_id = db.Column(db.ForeignKey('exam_type.id'), nullable=False, index=True)
    name = db.Column(db.String(300), nullable=False)
    session = db.Column(db.String(20), default='')
    variant = db.Column(db.String(120), default='')
    source_url = db.Column(db.Text)
    status = db.Column(db.String(32), default='CATALOG_ONLY', index=True)
    duration_seconds = db.Column(db.Integer)
    warnings = db.Column(db.JSON, default=list)
    source_metadata = db.Column(db.JSON, default=dict)
    canonical_paper_id = db.Column(db.ForeignKey('paper.id'))
    course = db.relationship(Course)
    term = db.relationship(Term)
    exam_type = db.relationship(ExamType)

class SourceEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    identity = db.Column(db.String(64), unique=True, nullable=False)
    paper_id = db.Column(db.ForeignKey('paper.id'), nullable=False)
    workbook_hash = db.Column(db.String(64), nullable=False)
    sheet = db.Column(db.String(100), nullable=False)
    cell = db.Column(db.String(20), nullable=False)
    raw_text = db.Column(db.Text)
    url = db.Column(db.Text)

class Question(db.Model):
    __table_args__ = (db.Index('ix_question_paper_status_id','paper_id','status','id'),)
    id = db.Column(db.Integer, primary_key=True)
    paper_id = db.Column(db.ForeignKey('paper.id'), nullable=False, index=True)
    number = db.Column(db.String(40), nullable=False)
    kind = db.Column(db.String(24), nullable=False)
    text = db.Column(db.Text, nullable=False)
    answers = db.Column(db.JSON)
    answer_status = db.Column(db.String(40), default='ANSWER_UNAVAILABLE')
    explanation = db.Column(db.Text)
    marks = db.Column(db.Float)
    negative_marks = db.Column(db.Float)
    tolerance = db.Column(db.Float, default=0)
    topic = db.Column(db.String(150), index=True)
    difficulty = db.Column(db.String(30))
    source_page = db.Column(db.Integer)
    ingestion_file_id = db.Column(db.ForeignKey('ingestion_file.id'))
    status = db.Column(db.String(30), default='EXTRACTED', index=True)
    source_pages = db.Column(db.JSON, default=list)
    evidence = db.Column(db.JSON, default=dict)
    fingerprint = db.Column(db.String(64), index=True)
    confidence = db.Column(db.Float, default=0)
    warnings = db.Column(db.JSON, default=list)
    created_at = db.Column(db.Float, default=time.time)
    updated_at = db.Column(db.Float, default=time.time, onupdate=time.time)
    options = db.relationship('QuestionOption', cascade='all, delete-orphan', order_by='QuestionOption.position')
    images = db.relationship('QuestionImage', cascade='all, delete-orphan')

class QuestionOption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.ForeignKey('question.id'), nullable=False, index=True)
    key = db.Column(db.String(20), nullable=False)
    text = db.Column(db.Text, nullable=False)
    position = db.Column(db.Integer, nullable=False)
    __table_args__ = (db.UniqueConstraint('question_id', 'key'),)

class QuestionImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.ForeignKey('question.id'), nullable=False, index=True)
    path = db.Column(db.String(200), nullable=False)
    alt = db.Column(db.String(200), default='Question diagram')
    option_key = db.Column(db.String(20))
    source_page = db.Column(db.Integer)

class PaperProgress(db.Model):
    """Only permanent exam outcome: one latest percentage per user and paper."""
    user_id = db.Column(db.ForeignKey('user.id'), primary_key=True)
    paper_id = db.Column(db.ForeignKey('paper.id'), primary_key=True)
    attempted = db.Column(db.Boolean, nullable=False, default=True)
    last_score = db.Column(db.Float)  # Percentage; NULL when source grading is incomplete.
    last_attempted_at = db.Column(db.Float, nullable=False)

class Attempt(db.Model):
    # Expired session URLs must never resolve to a later session on SQLite.
    __table_args__ = (db.Index('ix_attempt_user_status','user_id','status'), {'sqlite_autoincrement': True})
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.ForeignKey('user.id'), nullable=False, index=True)
    paper_id = db.Column(db.ForeignKey('paper.id'), index=True)
    mode = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    started_at = db.Column(db.Float, default=time.time)
    deadline = db.Column(db.Float, index=True)
    expires_at = db.Column(db.Float, nullable=False, index=True, default=lambda: time.time()+7*86400)
    records_progress = db.Column(db.Boolean, nullable=False, default=True)
    submitted_at = db.Column(db.Float)
    status = db.Column(db.String(20), default='ACTIVE', index=True)
    result = db.Column(db.JSON)
    version = db.Column(db.Integer, default=1, nullable=False)
    __mapper_args__ = {'version_id_col': version}
    items = db.relationship('AttemptAnswer', cascade='all, delete-orphan', order_by='AttemptAnswer.position')

class AttemptAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.ForeignKey('attempt.id'), nullable=False, index=True)
    question_id = db.Column(db.ForeignKey('question.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    snapshot = db.Column(db.JSON, nullable=False)
    answer = db.Column(db.JSON)
    visited = db.Column(db.Boolean, default=False)
    response_touched = db.Column(db.Boolean, default=False)
    marked = db.Column(db.Boolean, default=False)
    outcome = db.Column(db.String(20))
    awarded = db.Column(db.Float)
    manual_note = db.Column(db.Text)
    __table_args__ = (db.UniqueConstraint('attempt_id', 'question_id'),)

class Bookmark(db.Model):
    user_id = db.Column(db.ForeignKey('user.id'), primary_key=True)
    question_id = db.Column(db.ForeignKey('question.id'), primary_key=True)
    created_at = db.Column(db.Float, default=time.time)

class IngestionBatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.ForeignKey('user.id'),nullable=False)
    created_at = db.Column(db.Float, default=time.time)
    status = db.Column(db.String(30), default='QUEUED')

class IngestionFile(db.Model):
    __table_args__ = (db.Index('ix_ingestion_file_status_id','status','id'),)
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.ForeignKey('ingestion_batch.id'), nullable=False, index=True)
    paper_id = db.Column(db.ForeignKey('paper.id'), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    path = db.Column(db.String(100))
    file_hash = db.Column(db.String(64), unique=True)
    status = db.Column(db.String(30), default='QUEUED', index=True)
    error = db.Column(db.Text)
    warnings = db.Column(db.JSON, default=list)
    pages = db.Column(db.Integer)
    extracted = db.Column(db.Integer, default=0)
    started_at = db.Column(db.Float)
    finished_at = db.Column(db.Float)
    retries = db.Column(db.Integer, default=0)
    source_url = db.Column(db.Text)
    duplicate_of_id = db.Column(db.ForeignKey('ingestion_file.id'))
    events = db.Column(db.JSON, default=list)

class ImportRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.Float, default=time.time)
    workbook_hash = db.Column(db.String(64))
    report = db.Column(db.JSON)

class ExternalCredential(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(40), unique=True, nullable=False)
    account_email = db.Column(db.String(254))
    refresh_token_enc = db.Column(db.Text, nullable=False)
    scope = db.Column(db.Text)
    created_at = db.Column(db.Float, default=time.time, nullable=False)
    updated_at = db.Column(db.Float, default=time.time, onupdate=time.time, nullable=False)

class QuestionReview(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.ForeignKey('question.id'), nullable=False, index=True)
    user_id = db.Column(db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(30), nullable=False)
    before = db.Column(db.JSON)
    after = db.Column(db.JSON)
    created_at = db.Column(db.Float, default=time.time)
