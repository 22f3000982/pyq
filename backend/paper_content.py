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
        result=[question_snapshot(q) for q in sorted(rows,key=lambda q:(question_order(q.number),q.id))]
        # Older imports tagged comprehension questions but stored passage+prompt
        # together. Consecutive children share the exact passage prefix, so infer
        # it once at paper level instead of guessing from the first paragraph.
        i=0
        while i<len(result):
            if not result[i].get('shared_passage') or result[i].get('passage'):
                i+=1;continue
            j=i
            while j<len(result) and result[j].get('shared_passage') and not result[j].get('passage'):j+=1
            group=result[i:j]
            if len(group)>=2:
                texts=[x.get('text','') for x in group]
                prefix=texts[0]
                for value in texts[1:]:
                    n=0;limit=min(len(prefix),len(value))
                    while n<limit and prefix[n]==value[n]:n+=1
                    prefix=prefix[:n]
                    if not prefix:break
                cut=prefix.rfind('\n\n')
                if cut>20:
                    passage=prefix[:cut].strip()
                    for item in group:
                        if item['text'].startswith(passage):
                            item['passage']=passage
                            item['text']=item['text'][len(passage):].lstrip()
            i=j
        return result
    return cached('paper:'+str(paper_id)+':snapshots:msq-proportional-v1',load)
