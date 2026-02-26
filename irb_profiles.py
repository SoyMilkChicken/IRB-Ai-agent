"""Institution-specific IRB profile mappings and readiness config.

These profiles define:
- Required intake fields for a draft packet
- Section mappings between IRB form sections and app sources
- Required/generated/manual attachments

Start with a generic classroom research profile and extend per institution.
"""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


DEFAULT_IRB_PROFILE_ID = "generic_classroom_research_us_v1"


IRB_PROFILES: dict[str, dict[str, Any]] = {
    "generic_classroom_research_us_v1": {
        "id": "generic_classroom_research_us_v1",
        "name": "Generic U.S. Classroom Research (AI Grading) - v1",
        "shortName": "Generic Classroom IRB v1",
        "description": (
            "A generic profile for classroom-based human-subjects research involving students/TAs/instructors, "
            "with emphasis on recruitment power dynamics, FERPA-related concerns, and draft packet readiness."
        ),
        "irbOfficeLabel": "Institutional Review Board (Generic U.S. workflow)",
        "version": "1.0",
        "requiredIntakeFields": [
            {"key": "studyTitle", "label": "Study Title", "type": "text"},
            {"key": "institution", "label": "Institution", "type": "text"},
            {"key": "courseName", "label": "Course / Program Context", "type": "text"},
            {"key": "projectPurpose", "label": "Project Purpose", "type": "text"},
            {"key": "participantGroups", "label": "Participant Groups", "type": "multi_select"},
            {"key": "dataCollectionMethods", "label": "Data Collection Methods", "type": "multi_select"},
            {
                "key": "recruiterRole",
                "label": "Recruiter Role",
                "type": "select",
                "disallowValues": ["", "undecided"],
            },
            {
                "key": "includesMinors",
                "label": "Minor Participant Status",
                "type": "select",
                "disallowValues": ["", "unknown"],
            },
            {"key": "storageLocation", "label": "Data Storage Location", "type": "text"},
            {"key": "accessRoles", "label": "Data Access Roles", "type": "text"},
            {"key": "retentionPeriod", "label": "Retention / Deletion Timeline", "type": "text"},
            {
                "key": "identifierTypes",
                "label": "Identifier Types (if identifiers are collected)",
                "type": "multi_select",
                "conditional": {"fieldTruthy": "collectsIdentifiers"},
            },
        ],
        "requiredGeneratedDrafts": [
            {"docType": "consent", "label": "Consent Form Draft"},
            {"docType": "recruitment", "label": "Recruitment Message Draft"},
            {"docType": "data_handling", "label": "Data Handling Summary Draft"},
        ],
        "requiredManualAttachments": [
            {
                "id": "survey_instrument_copy",
                "label": "Survey Instrument / Question List",
                "reason": "IRB reviewers often request the full survey instrument as an attachment.",
                "conditional": {"methodIn": ["survey"]},
            },
            {
                "id": "interview_guide",
                "label": "Interview / Focus Group Guide",
                "reason": "Interview and focus group prompts are usually reviewed as study materials.",
                "conditional": {"methodIn": ["interview", "focus_group"]},
            },
            {
                "id": "data_coding_or_linkage_plan",
                "label": "Coding / Linkage Key Handling Description",
                "reason": "If identifiers are collected, the IRB may ask for how the linkage key is protected/destroyed.",
                "conditional": {"fieldTruthy": "collectsIdentifiers"},
            },
        ],
        "recommendedManualAttachments": [
            {
                "id": "advisor_review_notes",
                "label": "Faculty Advisor Review Notes",
                "reason": "Recommended before submission for student-led research projects.",
            }
        ],
        "sectionMappings": [
            {
                "sectionId": "study_title",
                "sectionLabel": "Study Title",
                "required": True,
                "sourceType": "intake",
                "sourceKey": "studyTitle",
                "notes": "IRB application title should match consent/recruitment materials.",
            },
            {
                "sectionId": "research_purpose",
                "sectionLabel": "Purpose / Research Question Summary",
                "required": True,
                "sourceType": "intake",
                "sourceKey": "projectPurpose",
                "notes": "Use plain language and align with the protocol narrative.",
            },
            {
                "sectionId": "participant_population",
                "sectionLabel": "Participant Population and Recruitment Source",
                "required": True,
                "sourceType": "derived",
                "sourceKey": "participants_and_recruiter",
                "notes": "Combine participant groups and recruiter role with voluntariness protections.",
            },
            {
                "sectionId": "procedures",
                "sectionLabel": "Study Procedures / Data Collection",
                "required": True,
                "sourceType": "intake",
                "sourceKey": "dataCollectionMethods",
                "notes": "List surveys/interviews/LMS data/etc. plus estimated time in final draft.",
            },
            {
                "sectionId": "risks_and_protections",
                "sectionLabel": "Risks, Coercion Protections, and Mitigations",
                "required": True,
                "sourceType": "derived",
                "sourceKey": "evaluation_flags",
                "notes": "Use risk flags as a checklist; final wording belongs in protocol and consent.",
            },
            {
                "sectionId": "confidentiality_data_security",
                "sectionLabel": "Confidentiality / Data Security Plan",
                "required": True,
                "sourceType": "generated_doc",
                "sourceKey": "data_handling",
                "notes": "Review and replace placeholders before submission.",
            },
            {
                "sectionId": "consent_process",
                "sectionLabel": "Consent Process and Consent Form",
                "required": True,
                "sourceType": "generated_doc",
                "sourceKey": "consent",
                "notes": "Generated consent draft should be edited to institution template language.",
            },
            {
                "sectionId": "recruitment_materials",
                "sectionLabel": "Recruitment Materials",
                "required": True,
                "sourceType": "generated_doc",
                "sourceKey": "recruitment",
                "notes": "Recruitment language should avoid coercive wording.",
            },
            {
                "sectionId": "retention_and_disposal",
                "sectionLabel": "Retention and Disposal Timeline",
                "required": True,
                "sourceType": "intake",
                "sourceKey": "retentionPeriod",
                "notes": "Should align with institutional policy and consent language.",
            },
            {
                "sectionId": "materials_attachments",
                "sectionLabel": "Study Materials Attachments",
                "required": True,
                "sourceType": "manual_attachment_bundle",
                "sourceKey": "materials_bundle",
                "notes": "Survey instruments/interview guides usually need separate attachments.",
            },
        ],
    }
}


def list_irb_profiles() -> list[dict[str, Any]]:
    """Return lightweight metadata for profile pickers."""
    items: list[dict[str, Any]] = []
    for profile in IRB_PROFILES.values():
        items.append(
            {
                "id": profile["id"],
                "name": profile["name"],
                "shortName": profile.get("shortName", profile["name"]),
                "description": profile.get("description", ""),
                "irbOfficeLabel": profile.get("irbOfficeLabel", "IRB"),
                "version": profile.get("version", "1.0"),
            }
        )
    return items


def get_irb_profile(profile_id: str | None) -> dict[str, Any]:
    if profile_id and profile_id in IRB_PROFILES:
        return IRB_PROFILES[profile_id]
    return IRB_PROFILES[DEFAULT_IRB_PROFILE_ID]


def profile_exists(profile_id: str) -> bool:
    return profile_id in IRB_PROFILES


def make_imported_profile_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    base = f"imported_{slug or 'organization'}_v1"
    candidate = base
    suffix = 2
    while candidate in IRB_PROFILES:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def upsert_irb_profile(profile: dict[str, Any]) -> dict[str, Any]:
    profile_id = str(profile.get("id", "")).strip()
    if not profile_id:
        raise ValueError("Profile must include a non-empty 'id'.")
    if not str(profile.get("name", "")).strip():
        raise ValueError("Profile must include a non-empty 'name'.")

    existing = IRB_PROFILES.get(profile_id, {})
    merged = deepcopy(existing)
    merged.update(deepcopy(profile))
    IRB_PROFILES[profile_id] = merged
    return merged
