#!/usr/bin/env python3
"""Minimal IRB Copilot MVP server.

Features:
- Serves a static wizard UI from ./static
- Rule-based IRB risk screening endpoint
- AI drafting/rewrite endpoints with template fallback

No third-party dependencies required.
"""

from __future__ import annotations

import json
import os
import re
import textwrap
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"


def _cors_allowed_origins() -> set[str]:
    raw = _str(os.environ.get("CORS_ALLOW_ORIGINS"))
    if not raw:
        return set()
    return {item.strip() for item in raw.split(",") if item.strip()}


def _origin_allowed(origin: str | None) -> bool:
    if not origin:
        return True
    allowed = _cors_allowed_origins()
    if not allowed:
        return False
    return "*" in allowed or origin in allowed


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return False


def _str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_str(v) for v in value if _str(v)]
    if isinstance(value, str):
        if "," in value:
            return [part.strip() for part in value.split(",") if part.strip()]
        return [value.strip()] if value.strip() else []
    return [_str(value)]


def _title_case_words(words: list[str]) -> str:
    return ", ".join(w.replace("_", " ").title() for w in words if w)


@dataclass
class Flag:
    code: str
    title: str
    severity: str  # high | medium | low
    rationale: str
    actions: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "title": self.title,
            "severity": self.severity,
            "rationale": self.rationale,
            "actions": self.actions,
        }


def evaluate_irb_risks(intake: dict[str, Any]) -> dict[str, Any]:
    participants = set(_list(intake.get("participantGroups")))
    methods = set(_list(intake.get("dataCollectionMethods")))
    recruiter_role = _str(intake.get("recruiterRole")) or "undecided"
    includes_minors = _str(intake.get("includesMinors")).lower() or "unknown"

    participation_voluntary = _bool(intake.get("participationVoluntary"))
    offers_extra_credit = _bool(intake.get("offersExtraCredit"))
    alternative_activity = _bool(intake.get("alternativeActivityProvided"))
    ai_affects_official_grades = _bool(intake.get("aiAffectsOfficialGrades"))
    research_separate_from_grades = _bool(intake.get("researchSeparateFromGrades"))

    collects_identifiers = _bool(intake.get("collectsIdentifiers"))
    identifier_types = set(_list(intake.get("identifierTypes")))
    collects_education_records = _bool(intake.get("collectsEducationRecords"))
    collects_sensitive = _bool(intake.get("collectsSensitive"))
    deidentify_before_analysis = _bool(intake.get("deidentifyBeforeAnalysis"))

    storage_location = _str(intake.get("storageLocation"))
    access_roles = _str(intake.get("accessRoles"))
    retention_period = _str(intake.get("retentionPeriod"))
    third_party_tools = _str(intake.get("thirdPartyTools"))

    flags: list[Flag] = []

    def add_flag(code: str, title: str, severity: str, rationale: str, actions: list[str]) -> None:
        flags.append(Flag(code, title, severity, rationale, actions))

    likely_human_subjects = bool(
        participants & {"students", "tas", "instructors"} and methods
    )

    if "students" in participants and recruiter_role in {"instructor", "ta"}:
        add_flag(
            "power_imbalance_recruitment",
            "Power Imbalance in Recruitment",
            "high",
            "Students may feel pressure to participate when recruited by the instructor or TA involved in the course.",
            [
                "Use a neutral recruiter when possible (advisor or research staff).",
                "State clearly that participation is voluntary and non-participation has no academic penalty.",
                "Delay access to participation records until grading is complete, if feasible.",
            ],
        )

    if offers_extra_credit and not alternative_activity:
        add_flag(
            "extra_credit_no_alternative",
            "Extra Credit Without Alternative",
            "high",
            "Offering course credit without an equivalent non-research option can create undue influence.",
            [
                "Provide an equivalent alternative activity for the same credit.",
                "Document how the alternative is comparable in effort and grading impact.",
            ],
        )

    if ai_affects_official_grades:
        add_flag(
            "ai_grade_impact",
            "AI Output Affects Official Grades",
            "high",
            "Using AI-generated scoring in official grading during research may increase risk and require stronger protections/oversight.",
            [
                "Consider a research phase where AI scores do not affect official grades.",
                "If grade impact remains, describe validation, appeal process, and human override steps.",
            ],
        )

    if not participation_voluntary:
        add_flag(
            "participation_not_clearly_voluntary",
            "Voluntariness Not Clear",
            "high",
            "IRBs typically expect explicit voluntary participation language for student research participation.",
            [
                "Add clear voluntariness statements to consent and recruitment materials.",
                "Describe how students may decline/withdraw without penalty.",
            ],
        )

    ferpa_risk = bool(collects_education_records or ai_affects_official_grades or "lms_data" in methods)
    if ferpa_risk:
        add_flag(
            "ferpa_records",
            "Potential FERPA / Education Records Concern",
            "high",
            "The study may involve education records or course performance information, which may trigger FERPA-related review and handling requirements.",
            [
                "Clarify whether any education records are used and under what authority/consent.",
                "Limit access to identifiable records and document role-based access.",
                "Describe de-identification or coded data handling steps.",
            ],
        )

    if collects_identifiers or identifier_types:
        add_flag(
            "identifiable_data",
            "Identifiable Data Collected",
            "medium",
            "Identifiers increase privacy/confidentiality risk and require stronger safeguards.",
            [
                "Minimize identifiers to only those required for the study.",
                "Separate identifiers from response data when possible.",
                "Document who can access the key and where it is stored.",
            ],
        )

    if collects_sensitive:
        add_flag(
            "sensitive_data",
            "Sensitive Data Collection",
            "medium",
            "Sensitive responses can increase risk beyond minimal risk depending on context and identifiability.",
            [
                "Limit sensitive questions to what is necessary.",
                "Describe safeguards and optional skip choices for sensitive questions.",
            ],
        )

    if includes_minors in {"yes", "unknown"}:
        add_flag(
            "minor_status_unclear",
            "Potential Minor Participants",
            "high" if includes_minors == "yes" else "medium",
            "If participants may be minors, parental permission/assent requirements may apply unless the IRB approves a waiver.",
            [
                "Confirm participant age range.",
                "Prepare assent/parent permission plan if minors are included.",
            ],
        )

    if "students" in participants and not research_separate_from_grades:
        add_flag(
            "grade_separation_unclear",
            "Research Access vs Grading Access Not Separated",
            "medium",
            "IRBs often look for process separation when the research team overlaps with grading authority.",
            [
                "Describe when identifiable participation data becomes visible to instructors/TAs.",
                "Consider delaying access until final grades are submitted.",
            ],
        )

    if (collects_identifiers or ferpa_risk) and not deidentify_before_analysis:
        add_flag(
            "deidentification_missing",
            "De-identification Plan Not Specified",
            "medium",
            "A clear de-identification/coding plan helps reduce privacy risk and supports minimal-risk justification.",
            [
                "Specify when identifiers are removed or replaced with study codes.",
                "State who holds the linkage key and when it will be destroyed.",
            ],
        )

    if not storage_location:
        add_flag(
            "storage_location_missing",
            "Storage Location Not Specified",
            "low",
            "The IRB application usually requires where research data will be stored.",
            ["Add a storage location (e.g., university-approved encrypted drive, secure cloud)."],
        )

    if not access_roles:
        add_flag(
            "access_roles_missing",
            "Data Access Roles Not Specified",
            "low",
            "Reviewers often ask who will have access to identifiable and de-identified data.",
            ["Describe access by role (PI, TA, advisor, analyst)."],
        )

    if not retention_period:
        add_flag(
            "retention_period_missing",
            "Retention / Deletion Timeline Missing",
            "low",
            "IRB reviewers typically expect a retention and deletion or archival timeline.",
            ["Add how long data will be kept and when/how it will be deleted or archived."],
        )

    if third_party_tools:
        add_flag(
            "third_party_tools",
            "Third-Party Tool Review Needed",
            "low",
            "Third-party platforms may introduce data transfer/storage considerations that should be disclosed.",
            [
                "List each tool and what data it receives.",
                "Confirm whether institutional approval is needed for those tools.",
            ],
        )

    severity_rank = {"high": 3, "medium": 2, "low": 1}
    highest_severity = max((severity_rank[f.severity] for f in flags), default=1)
    likely_minimal_risk = highest_severity < 3 and not collects_sensitive
    if ai_affects_official_grades or (collects_sensitive and (collects_identifiers or ferpa_risk)):
        likely_minimal_risk = False

    next_steps = []
    if any(f.severity == "high" for f in flags):
        next_steps.append("Address high-severity flags before drafting final submission language.")
    if "power_imbalance_recruitment" in {f.code for f in flags}:
        next_steps.append("Design a neutral recruitment process or explain protections against coercion.")
    if "ferpa_records" in {f.code for f in flags}:
        next_steps.append("Clarify whether education records are used and describe FERPA safeguards.")
    if not next_steps:
        next_steps.append("Draft materials and verify them against your institution's IRB form requirements.")

    summary = {
        "likelyHumanSubjectsResearch": likely_human_subjects,
        "likelyMinimalRisk": likely_minimal_risk,
        "flagCounts": {
            "high": sum(1 for f in flags if f.severity == "high"),
            "medium": sum(1 for f in flags if f.severity == "medium"),
            "low": sum(1 for f in flags if f.severity == "low"),
        },
        "participants": sorted(participants),
        "methods": sorted(methods),
        "notes": [
            "This tool provides drafting and pre-screening support only; it does not approve IRB submissions.",
            "Final materials should be reviewed by the PI/faculty advisor and your IRB office.",
        ],
        "nextSteps": next_steps,
    }

    return {
        "summary": summary,
        "flags": [f.as_dict() for f in sorted(flags, key=lambda f: severity_rank[f.severity], reverse=True)],
    }


def _participant_label(intake: dict[str, Any]) -> str:
    groups = _list(intake.get("participantGroups"))
    return _title_case_words(groups) or "Participants"


def _method_label(intake: dict[str, Any]) -> str:
    methods = _list(intake.get("dataCollectionMethods"))
    if not methods:
        return "surveys and related study activities"
    return _title_case_words(methods)


def build_template_draft(doc_type: str, intake: dict[str, Any], evaluation: dict[str, Any]) -> str:
    title = _str(intake.get("studyTitle")) or "Untitled Study"
    course = _str(intake.get("courseName")) or "[Course Name]"
    institution = _str(intake.get("institution")) or "[Institution Name]"
    purpose = _str(intake.get("projectPurpose")) or "[Describe the purpose of the research study.]"
    participants = _participant_label(intake)
    methods = _method_label(intake)

    collects_identifiers = _bool(intake.get("collectsIdentifiers"))
    deidentify = _bool(intake.get("deidentifyBeforeAnalysis"))
    storage_location = _str(intake.get("storageLocation")) or "[Storage location]"
    access_roles = _str(intake.get("accessRoles")) or "[List who has access]"
    retention = _str(intake.get("retentionPeriod")) or "[Retention period]"
    recruiter_role = _str(intake.get("recruiterRole")) or "research team member"
    participation_voluntary = _bool(intake.get("participationVoluntary"))
    offers_extra_credit = _bool(intake.get("offersExtraCredit"))
    alternative_activity = _bool(intake.get("alternativeActivityProvided"))
    ai_affects_official_grades = _bool(intake.get("aiAffectsOfficialGrades"))
    third_party_tools = _str(intake.get("thirdPartyTools"))

    flag_titles = [f["title"] for f in evaluation.get("flags", [])]
    flag_note = "; ".join(flag_titles[:4]) if flag_titles else "No major risk flags were identified by the pre-screen."

    if doc_type == "consent":
        grade_statement = (
            "Participation or non-participation will not affect course grades, academic standing, or relationship with the instructor/TA."
            if not ai_affects_official_grades
            else "Because this study involves an AI grading tool related to course work, the research team will describe in detail how official grading decisions are reviewed by humans and how participants can raise concerns."
        )
        extra_credit_statement = ""
        if offers_extra_credit:
            if alternative_activity:
                extra_credit_statement = (
                    "If extra credit is offered, an equivalent non-research alternative will be available for the same credit."
                )
            else:
                extra_credit_statement = (
                    "If extra credit is offered, the research team must add an equivalent non-research alternative before IRB submission."
                )

        return textwrap.dedent(
            f"""
            DRAFT CONSENT FORM (For IRB Preparation Only)
            Study Title: {title}
            Institution: {institution}
            Course Context: {course}

            Purpose of the Study
            You are invited to take part in a research study about an AI-assisted grading tool and its impact on instruction and learning. The purpose of this study is: {purpose}

            Why You Were Invited
            You are being invited because you are part of the following participant group(s): {participants}.

            What You Will Be Asked To Do
            If you choose to participate, you may be asked to complete one or more of the following: {methods}. The study team should update this section with expected time, number of sessions, and any follow-up activities.

            Voluntary Participation
            {"Your participation is voluntary. You may decline to participate or stop at any time without penalty." if participation_voluntary else "[Add explicit voluntary participation language here.]"}
            {grade_statement}
            {extra_credit_statement}

            Risks or Discomforts
            This study is expected to involve no more than minimal risk for most participants. Possible risks include privacy/confidentiality concerns if research data are linked to education records or identifiable information. The study team should tailor this section to the actual risks in the protocol.

            Benefits
            There may be no direct benefit to you. Potential benefits may include improvements to course assessment practices and better understanding of how AI-assisted grading tools affect instructors, TAs, and students.

            Confidentiality and Data Handling
            {"The study may collect identifiable information." if collects_identifiers else "The study is designed to avoid collecting direct identifiers where possible."}
            {"Data will be de-identified before analysis when feasible." if deidentify else "The de-identification plan should be described in detail before submission."}
            Research data will be stored at: {storage_location}
            Access to study data will be limited to: {access_roles}
            Data retention/deletion timeline: {retention}
            {"Third-party tools involved: " + third_party_tools if third_party_tools else ""}

            Questions
            For questions about the research, contact: [PI Name / Email]
            For questions about your rights as a research participant, contact: [IRB Office Contact]

            Consent
            By signing below (or selecting agree in an online form), you indicate that you are at least 18 years old or otherwise eligible to consent, have read this information, and agree to participate.

            Internal Copilot Note (remove before submission): {flag_note}
            """
        ).strip()

    if doc_type == "recruitment":
        recruiter_line = (
            "This message should ideally be sent by a neutral party rather than course grading staff."
            if recruiter_role in {"instructor", "ta"}
            else f"This message may be sent by the {recruiter_role.replace('_', ' ')}."
        )
        extra_credit_line = ""
        if offers_extra_credit:
            extra_credit_line = (
                "If participation involves extra credit, include the equivalent non-research alternative and state that choosing the alternative will not disadvantage students."
            )
        return textwrap.dedent(
            f"""
            DRAFT RECRUITMENT MESSAGE (For IRB Preparation Only)

            Subject: Invitation to Participate in Research Study About AI-Assisted Grading

            Hello,

            You are invited to participate in a research study related to {title} in the context of {course} at {institution}.

            What the study is about:
            {purpose}

            What participation may involve:
            - {methods}
            - Time commitment: [Insert estimate]
            - Format: [Online survey / interview / other]

            Participation is voluntary. Choosing not to participate will not affect your grades, academic standing, or relationship with your instructor, TA, or institution.
            You may stop participating at any time without penalty.
            {extra_credit_line}

            If you are interested, please review the consent information here: [Insert link or attachment]
            To participate, follow this link: [Insert survey/interview sign-up link]

            {recruiter_line}

            Questions can be directed to: [PI Name / Email]

            Internal Copilot Note (remove before submission): {flag_note}
            """
        ).strip()

    if doc_type == "data_handling":
        return textwrap.dedent(
            f"""
            DRAFT DATA HANDLING SUMMARY (For IRB Preparation Only)

            Study Title: {title}
            Project Purpose Summary:
            {purpose}

            Data Types Collected
            - Participant groups: {participants}
            - Collection methods: {methods}
            - Identifiers collected: {"Yes" if collects_identifiers else "No / minimal"}
            - Identifier types: {_title_case_words(sorted(_list(intake.get("identifierTypes")))) or "Not specified"}
            - Education records / course performance data: {"Yes" if _bool(intake.get("collectsEducationRecords")) else "No / not specified"}
            - Sensitive data: {"Yes" if _bool(intake.get("collectsSensitive")) else "No / not specified"}

            Data Minimization
            The study team should collect only data needed to answer the research questions and avoid unnecessary identifiers.

            De-identification / Coding Plan
            {"Data will be de-identified before analysis when feasible." if deidentify else "A de-identification/coding plan has not yet been specified and should be added before submission."}
            If a linkage key is used, describe where it is stored, who can access it, and when it will be destroyed.

            Storage and Security
            - Storage location: {storage_location}
            - Access roles: {access_roles}
            - Retention period: {retention}
            - Third-party tools/services: {third_party_tools or "None listed"}
            - Transmission/security controls: [Add encryption / secure transfer details]

            FERPA / Educational Records Considerations
            {"This project may involve education records or course-related performance data and should include a FERPA-compliant access/consent justification." if any(f["code"] == "ferpa_records" for f in evaluation.get("flags", [])) else "No FERPA-related flag was triggered in the pre-screen, but confirm against institutional policy."}

            Access Separation (if instructor/TA overlap exists)
            If course staff are also researchers, describe how access to identifiable research participation data is separated from grading decisions and when identifiable data become visible.

            Internal Copilot Note (remove before submission): {flag_note}
            """
        ).strip()

    raise ValueError(f"Unsupported doc_type: {doc_type}")


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", text.strip()))


def rewrite_text_fallback(text: str, goal: str) -> str:
    if not text.strip():
        return ""

    result = text
    if goal == "less_coercive":
        replacements = [
            (r"\bmust participate\b", "may choose to participate"),
            (r"\bshould participate\b", "are invited to participate"),
            (r"\byou are required to\b", "you may choose to"),
            (r"\byou need to\b", "you may"),
            (r"\bwill receive extra credit for participating\b", "may be eligible for extra credit if participating, and an equivalent non-research alternative will be available"),
        ]
        for pattern, repl in replacements:
            result = re.sub(pattern, repl, result, flags=re.IGNORECASE)

        if "voluntary" not in result.lower():
            result += "\n\nParticipation is voluntary. Choosing not to participate will not affect grades, standing, or your relationship with course staff."

        if "without penalty" not in result.lower():
            result += "\nYou may decline or withdraw at any time without penalty."

        return _normalize_whitespace(result)

    if goal == "clearer":
        # Light-touch clarity edits without changing meaning.
        replacements = [
            ("in order to", "to"),
            ("utilize", "use"),
            ("prior to", "before"),
            ("subsequent to", "after"),
            ("commence", "start"),
            ("terminate", "end"),
            ("participants will be asked to", "you may be asked to"),
        ]
        for old, new in replacements:
            result = re.sub(re.escape(old), new, result, flags=re.IGNORECASE)

        lines = []
        for raw_line in result.splitlines():
            line = raw_line.strip()
            if len(line) > 180 and not line.startswith("-"):
                parts = re.split(r"(?<=[.!?])\s+", line)
                lines.extend(parts)
            else:
                lines.append(raw_line)
        return _normalize_whitespace("\n".join(lines))

    return _normalize_whitespace(result)


def _openai_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _call_openai_chat(system_prompt: str, user_prompt: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    api_url = os.environ.get("OPENAI_CHAT_API_URL", "https://api.openai.com/v1/chat/completions")
    model = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    req = urlrequest.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=45) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API error ({exc.code}): {detail[:400]}") from exc
    except urlerror.URLError as exc:
        raise RuntimeError(f"OpenAI API network error: {exc.reason}") from exc

    try:
        return body["choices"][0]["message"]["content"].strip()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("Unexpected OpenAI API response format") from exc


def ai_or_template_draft(doc_type: str, intake: dict[str, Any], evaluation: dict[str, Any]) -> dict[str, Any]:
    template_text = build_template_draft(doc_type, intake, evaluation)
    if not _openai_available():
        return {
            "text": template_text,
            "mode": "template_fallback",
            "warning": "OPENAI_API_KEY not configured; returned template-based draft.",
        }

    system_prompt = (
        "You are an IRB drafting copilot. Produce concise, clear draft language for IRB preparation. "
        "Do not claim approval. Preserve voluntariness and privacy safeguards. "
        "If there are risk flags, address them with neutral wording and placeholders where institution-specific details are needed."
    )
    user_prompt = (
        f"Document type: {doc_type}\n"
        f"Project intake JSON:\n{json.dumps(intake, indent=2)}\n\n"
        f"IRB pre-screen evaluation JSON:\n{json.dumps(evaluation, indent=2)}\n\n"
        "Create a polished draft suitable for human review. Include a clear header that this is a draft for IRB preparation only."
    )
    try:
        return {
            "text": _call_openai_chat(system_prompt, user_prompt),
            "mode": "openai",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "text": template_text,
            "mode": "template_fallback",
            "warning": f"AI call failed; returned template draft instead. {exc}",
        }


def ai_or_fallback_rewrite(text: str, goal: str, intake: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = rewrite_text_fallback(text, goal)
    if not _openai_available():
        return {
            "text": fallback,
            "mode": "template_fallback",
            "warning": "OPENAI_API_KEY not configured; returned rule-based rewrite.",
        }

    goal_instruction = {
        "less_coercive": "Rewrite to reduce coercive tone, emphasize voluntariness, and avoid pressure, while preserving meaning.",
        "clearer": "Rewrite for plain language clarity and readability without changing substantive meaning.",
    }.get(goal, "Rewrite for clarity.")

    system_prompt = (
        "You revise IRB-related draft language. Keep the meaning and protections intact. "
        "Do not remove voluntariness or confidentiality statements. Return only the revised text."
    )
    intake_json = json.dumps(intake or {}, indent=2)
    user_prompt = (
        f"Goal: {goal}\n"
        f"Instruction: {goal_instruction}\n"
        f"Project context (optional):\n{intake_json}\n\n"
        f"Text to revise:\n{text}"
    )
    try:
        return {
            "text": _call_openai_chat(system_prompt, user_prompt),
            "mode": "openai",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "text": fallback,
            "mode": "template_fallback",
            "warning": f"AI call failed; returned rule-based rewrite instead. {exc}",
        }


class IRBCopilotHandler(SimpleHTTPRequestHandler):
    server_version = "IRBCopilot/0.1"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep logs concise but visible during local development.
        print(f"[{self.log_date_time_string()}] {self.address_string()} - {fmt % args}")

    def _is_api_request(self) -> bool:
        return self.path.startswith("/api/")

    def _apply_cors_headers(self) -> None:
        if not self._is_api_request():
            return
        origin = self.headers.get("Origin")
        if not origin:
            return
        if not _origin_allowed(origin):
            return
        allowed = _cors_allowed_origins()
        if "*" in allowed:
            self.send_header("Access-Control-Allow-Origin", "*")
        else:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def end_headers(self) -> None:
        self._apply_cors_headers()
        super().end_headers()

    def _origin_matches_this_server(self, origin: str | None) -> bool:
        if not origin:
            return False
        host = _str(self.headers.get("Host"))
        if not host:
            return False
        candidates = {f"http://{host}", f"https://{host}"}
        forwarded_proto = _str(self.headers.get("X-Forwarded-Proto"))
        if forwarded_proto:
            for proto in forwarded_proto.split(","):
                proto = proto.strip()
                if proto:
                    candidates.add(f"{proto}://{host}")
        return origin in candidates

    def _reject_disallowed_cross_origin(self) -> bool:
        if not self._is_api_request():
            return False
        origin = self.headers.get("Origin")
        if origin and not (_origin_allowed(origin) or self._origin_matches_this_server(origin)):
            self._send_error_json(
                "CORS origin not allowed. Set CORS_ALLOW_ORIGINS on the backend.",
                status=403,
            )
            return True
        return False

    def _read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON body: {exc.msg}") from exc

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int = 400) -> None:
        self._send_json({"error": message}, status=status)

    def do_OPTIONS(self) -> None:  # noqa: N802
        if not self._is_api_request():
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        if self._reject_disallowed_cross_origin():
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self._is_api_request() and self._reject_disallowed_cross_origin():
            return
        if self.path == "/api/health":
            self._send_json(
                {
                    "ok": True,
                    "service": "IRB Copilot MVP",
                    "aiConfigured": _openai_available(),
                    "aiMode": "openai" if _openai_available() else "template_fallback",
                    "note": "This tool assists with drafting and pre-screening only; it does not approve IRB submissions.",
                }
            )
            return
        if self.path in {"/", "/index.html"}:
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self._reject_disallowed_cross_origin():
            return
        try:
            payload = self._read_json()
        except ValueError as exc:
            self._send_error_json(str(exc), status=400)
            return

        try:
            if self.path == "/api/evaluate":
                intake = payload.get("intake", {})
                if not isinstance(intake, dict):
                    raise ValueError("'intake' must be an object")
                result = evaluate_irb_risks(intake)
                self._send_json({"ok": True, "evaluation": result})
                return

            if self.path == "/api/draft":
                intake = payload.get("intake", {})
                evaluation = payload.get("evaluation", {})
                doc_type = _str(payload.get("docType"))
                if doc_type not in {"consent", "recruitment", "data_handling"}:
                    raise ValueError("docType must be one of: consent, recruitment, data_handling")
                if not isinstance(intake, dict):
                    raise ValueError("'intake' must be an object")
                if not isinstance(evaluation, dict):
                    raise ValueError("'evaluation' must be an object")
                result = ai_or_template_draft(doc_type, intake, evaluation)
                self._send_json({"ok": True, "draft": result})
                return

            if self.path == "/api/rewrite":
                text = _str(payload.get("text"))
                goal = _str(payload.get("goal"))
                intake = payload.get("intake", {})
                if goal not in {"less_coercive", "clearer"}:
                    raise ValueError("goal must be one of: less_coercive, clearer")
                result = ai_or_fallback_rewrite(text, goal, intake if isinstance(intake, dict) else None)
                self._send_json({"ok": True, "rewrite": result})
                return

            self._send_error_json("Unknown endpoint", status=404)
        except ValueError as exc:
            self._send_error_json(str(exc), status=400)
        except Exception as exc:  # noqa: BLE001
            self._send_error_json(f"Server error: {exc}", status=500)


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    if not STATIC_DIR.exists():
        raise SystemExit(f"Static directory not found: {STATIC_DIR}")
    with ThreadingHTTPServer((host, port), IRBCopilotHandler) as httpd:
        print(f"IRB Copilot MVP running on http://{host}:{port}")
        print("AI mode:", "OpenAI enabled" if _openai_available() else "Template fallback (no OPENAI_API_KEY)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down.")


if __name__ == "__main__":
    import argparse

    default_port = int(os.environ.get("PORT", "8000"))
    default_host = os.environ.get("HOST", "127.0.0.1")

    parser = argparse.ArgumentParser(description="Run the IRB Copilot MVP server")
    parser.add_argument("--host", default=default_host)
    parser.add_argument("--port", type=int, default=default_port)
    args = parser.parse_args()
    run_server(args.host, args.port)
