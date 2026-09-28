"""Exact source strings and decimal/fraction/range scoring without evaluation."""
import re
from decimal import Decimal,InvalidOperation
from fractions import Fraction
NUM=r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(?:\s*/\s*[+-]?\d+(?:\.\d+)?)?'
def number(value):
    s=str(value).strip().replace('−','-')
    if not re.fullmatch(NUM,s):raise ValueError('Not a finite numeric value')
    if '/' in s:
        a,b=s.split('/');d=Decimal(a.strip())/Decimal(b.strip())
    else:d=Decimal(s)
    if not d.is_finite():raise ValueError('Not finite')
    return d

def parse_numeric_key(raw):
    raw=raw.strip();s=raw.replace('−','-').replace('–','-')
    # Explicit inclusive range; signs remain part of individual numbers.
    m=re.fullmatch(r'\s*\[?\s*('+NUM+r')\s*(?:to|:|through|(?<=\d)\s+-\s+)\s*('+NUM+r')\s*\]?\s*',s,re.I)
    if m:
        lo,hi=m[1],m[2]
        if number(lo)>number(hi):raise ValueError('Reversed source numeric range')
        return {'kind':'range','raw':raw,'lower':lo,'upper':hi,'inclusive':True}
    vals=re.split(r'\s*(?:;|,|\bor\b|\|)\s*',s)
    if not vals or any(not re.fullmatch(NUM,v) for v in vals):raise ValueError('Unrecognized explicit numeric key')
    for v in vals:number(v)
    return {'kind':'values','raw':raw,'values':vals}

def numeric_correct(answer,key,tolerance=0):
    value=number(answer);tol=number(tolerance or 0)
    if isinstance(key,dict):
        if key.get('kind')=='alternatives':return any(numeric_correct(answer,k,tolerance) for k in key['keys'])
        if key.get('kind')=='range':return number(key['lower'])<=value<=number(key['upper'])
        if key.get('kind')=='values':return any(abs(value-number(v))<=tol for v in key['values'])
        raise ValueError('Unknown numeric key structure')
    return abs(value-number(key))<=tol
