"""Rule: no Werkstudent / working-student / internship / thesis roles, nothing requiring enrollment."""

from __future__ import annotations

import re

from job_search.models import Posting, Verdict
from job_search.verify.text import snippet

RULE = "enrollment"

_STUDENT_TITLE = re.compile(
    r"(werk\s*student\w*|working[- ]student|student(ische)?\s*(assistant|hilfskraft|mitarbeiter\w*|job|worker)|"
    r"\bhiwi\b|praktik\w*|\bintern\b|\binterns\b|internship|\bpraktika\b|"
    r"abschlussarbeit|masterarbeit|bachelorarbeit|master'?s? thesis|bachelor'?s? thesis|\bthesis\b|"
    r"duales? studium|dual(er)? student\w*|\bstudent\b)",
    re.IGNORECASE,
)
_ENROLLMENT_BODY = re.compile(
    r"(enrolled[^.;\n]{0,30}?(university|universität|hochschule|college|student|degree|studies|"
    r"study program\w*|bachelor|master|phd)|"
    r"enrol(l)?ment certificate|proof of enrol\w*|immatrikuliert|immatrikulationsbescheinigung|"
    r"eingeschrieben\w*[^.;\n]{0,20}?(hochschule|universität|studiengang)|"
    r"(currently|still) (studying|pursuing)|you are (currently )?(a )?(university )?student\b|"
    r"(laufendes|aktuelles) studium|du studierst|sie studieren|studierst (aktuell|derzeit|noch)|"
    r"(currently )?pursuing (a|your|an) (bachelor|master|phd|degree|university degree)|als werkstudent)",
    re.IGNORECASE,
)


def check(posting: Posting) -> Verdict:
    m = _STUDENT_TITLE.search(posting.title)
    if m:
        return Verdict.fail(RULE, f"student/intern/thesis role ('{m.group(0)}' in title)", posting.title)
    m = _ENROLLMENT_BODY.search(posting.description)
    if m:
        return Verdict.fail(RULE, "requires active university enrollment", snippet(posting.description, m))
    return Verdict.ok(RULE)
