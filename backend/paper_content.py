"""Shared source snapshots: keys stay server-side, independent of student state."""
from sqlalchemy.orm import selectinload, load_only
from .models import Question, QuestionOption, QuestionImage
from .engine import question_snapshot, question_order
from .content_cache import cached


def snapshots(paper_id):
    def load():
        rows=Question.query.options(
            load_only(Question.id,Question.paper_id,Question.number,Question.kind,Question.text,
                      Question.answers,Question.answer_status,Question.explanation,Question.marks,
                      Question.negative_marks,Question.tolerance,Question.topic,Question.difficulty,
                      Question.source_page,Question.source_pages,Question.evidence),
            selectinload(Question.options).load_only(QuestionOption.key,QuestionOption.text,QuestionOption.position),
            selectinload(Question.images).load_only(QuestionImage.id,QuestionImage.path,QuestionImage.alt,QuestionImage.option_key)
        ).filter_by(paper_id=paper_id,status='AVAILABLE').all()
        return [question_snapshot(q) for q in sorted(rows,key=lambda q:(question_order(q.number),q.id))]
    return cached('paper:'+str(paper_id)+':snapshots',load)
