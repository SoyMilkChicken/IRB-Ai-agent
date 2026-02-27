"""IRB profile importer.

Builds a draft institution profile from:
- organization name
- optional organization website / IRB page URL
- optional raw policy text

Design goals:
- Best-effort extraction with transparent confidence/warnings
- Safe fallback when network access or parsing fails
- Output compatible with IRB profile schema used by readiness checks
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
import ipaddress
import json
import re
import socket
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
from urllib import error as urlerror
from urllib import request as urlrequest


USER_AGENT = "IRB-Copilot-Importer/1.0 (+https://github.com/SoyMilkChicken/IRB-Ai-agent)"
REQUEST_TIMEOUT_SECONDS = 7
MAX_SOURCE_FETCH = 7
MAX_LINKS_PER_PAGE = 120
MAX_PDF_SOURCES_TO_PARSE = 2
MAX_TEXT_CHARS = 240_000
MAX_SOURCE_RESPONSE_BYTES = 2_500_000
MAX_REDIRECTS = 4
ALLOWED_FETCH_SCHEMES = {"http", "https"}
ALLOWED_FETCH_PORTS = {80, 443}
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "0.0.0.0",
    "127.0.0.1",
    "::1",
    "metadata.google.internal",
}
REDIRECT_HTTP_CODES = {301, 302, 303, 307, 308}


IRB_PAGE_HINTS = [
    "institutional review board",
    "human subjects",
    "hrpp",
    "research compliance",
    "irb",
]

SEARCH_QUERIES = [
    '"{name}" institutional review board',
    '"{name}" human subjects research',
    '"{name}" IRB application',
]

LIKELY_IRB_PATHS = [
    "/irb",
    "/research/irb",
    "/research-compliance/irb",
    "/research-compliance/human-subjects",
    "/human-subjects",
    "/hrpp",
    "/research/human-subjects",
]

REQUIREMENT_RULES = [
    {
        "id": "review_categories",
        "label": "Review Category Definitions",
        "patterns": [r"\bexempt\b", r"\bexpedited\b", r"\bfull[\s-]?board\b"],
        "weight": 0.12,
        "summary": "Review categories (exempt/expedited/full board) are referenced.",
    },
    {
        "id": "training",
        "label": "Human Subjects Training",
        "patterns": [r"\bciti\b", r"human subjects training", r"research ethics training"],
        "weight": 0.11,
        "summary": "Research training requirement language detected.",
    },
    {
        "id": "consent_template",
        "label": "Consent Template/Process",
        "patterns": [r"\bconsent\b", r"\binformed consent\b", r"consent template"],
        "weight": 0.1,
        "summary": "Consent requirements/templates are referenced.",
    },
    {
        "id": "recruitment_materials",
        "label": "Recruitment Materials",
        "patterns": [r"\brecruitment\b", r"recruitment script", r"participant invitation"],
        "weight": 0.08,
        "summary": "Recruitment material requirements are referenced.",
    },
    {
        "id": "survey_instrument",
        "label": "Survey/Instrument Attachment",
        "patterns": [r"survey instrument", r"questionnaire", r"interview guide", r"focus group guide"],
        "weight": 0.09,
        "summary": "Study instrument attachment requirements are referenced.",
    },
    {
        "id": "privacy_data_security",
        "label": "Privacy/Data Security",
        "patterns": [r"data security", r"confidentiality", r"data retention", r"encryption"],
        "weight": 0.1,
        "summary": "Data confidentiality/security requirements are referenced.",
    },
    {
        "id": "education_records",
        "label": "Education Records / FERPA",
        "patterns": [r"\bferpa\b", r"education records", r"student records"],
        "weight": 0.08,
        "summary": "FERPA or education-record references are detected.",
    },
    {
        "id": "minors_assent",
        "label": "Minors / Assent",
        "patterns": [r"\bminor(s)?\b", r"parental permission", r"\bassent\b"],
        "weight": 0.08,
        "summary": "Minor participant requirements are referenced.",
    },
    {
        "id": "hipaa_health_data",
        "label": "HIPAA / Health Data",
        "patterns": [r"\bhipaa\b", r"protected health information", r"\bphi\b"],
        "weight": 0.05,
        "summary": "Health-data/HIPAA language is referenced.",
    },
]


@dataclass
class SourceDoc:
    url: str
    source_type: str  # web | guessed | inline_text | search
    status: str = "unfetched"  # unfetched | fetched | failed
    http_status: int | None = None
    content_type: str = ""
    title: str = ""
    text: str = ""
    links: list[str] | None = None
    error: str | None = None

    def as_metadata(self, requirement_hits: dict[str, int]) -> dict[str, Any]:
        return {
            "url": self.url,
            "sourceType": self.source_type,
            "status": self.status,
            "httpStatus": self.http_status,
            "contentType": self.content_type,
            "title": self.title,
            "error": self.error or "",
            "matchedRequirementIds": sorted([rule_id for rule_id, count in requirement_hits.items() if count > 0]),
        }


class _LinkTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_script = False
        self._in_style = False
        self._title_active = False
        self._title_chunks: list[str] = []
        self._text_chunks: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "script":
            self._in_script = True
            return
        if tag == "style":
            self._in_style = True
            return
        if tag == "title":
            self._title_active = True
            return
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href.strip())

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "script":
            self._in_script = False
        elif tag == "style":
            self._in_style = False
        elif tag == "title":
            self._title_active = False

    def handle_data(self, data: str) -> None:
        if self._in_script or self._in_style:
            return
        text = data.strip()
        if not text:
            return
        if self._title_active:
            self._title_chunks.append(text)
        else:
            self._text_chunks.append(text)

    @property
    def title(self) -> str:
        return " ".join(self._title_chunks).strip()

    @property
    def text(self) -> str:
        return "\n".join(self._text_chunks)


def _str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _normalize_url(url: str) -> str:
    url = _str(url)
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme:
        return url
    if url.startswith("//"):
        return f"https:{url}"
    return f"https://{url}"


def _is_blocked_ip(ip: Any) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _host_resolves_to_blocked_ip(host: str) -> tuple[bool, str]:
    # First catch direct IP literals.
    try:
        direct_ip = ipaddress.ip_address(host)
        if _is_blocked_ip(direct_ip):
            return True, str(direct_ip)
        return False, ""
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        # Leave DNS failures to the normal fetch path.
        return False, ""

    for info in infos:
        resolved = _str(info[4][0]).split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(resolved)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            return True, resolved
    return False, ""


def _validate_fetch_url(url: str) -> tuple[bool, str]:
    parsed = urlparse(url)
    scheme = _str(parsed.scheme).lower()
    if scheme not in ALLOWED_FETCH_SCHEMES:
        return False, "Only http/https URLs are allowed."

    if parsed.username or parsed.password:
        return False, "URLs containing embedded credentials are blocked."

    host = (_str(parsed.hostname).lower().rstrip("."))
    if not host:
        return False, "URL host is missing."
    if host in BLOCKED_HOSTNAMES:
        return False, f"Blocked host '{host}'."

    try:
        port = parsed.port
    except ValueError:
        return False, "Invalid URL port."
    if port and port not in ALLOWED_FETCH_PORTS:
        return False, f"Blocked non-standard port '{port}'."

    blocked, ip_text = _host_resolves_to_blocked_ip(host)
    if blocked:
        return False, f"Resolved to private/local IP '{ip_text}'."

    return True, ""


def _read_response_payload(resp: Any) -> bytes:
    content_length = _str(resp.headers.get("Content-Length"))
    if content_length:
        try:
            declared = int(content_length)
        except ValueError:
            declared = 0
        if declared > MAX_SOURCE_RESPONSE_BYTES:
            raise ValueError(
                f"Response too large ({declared} bytes). Max is {MAX_SOURCE_RESPONSE_BYTES} bytes."
            )

    payload = resp.read(MAX_SOURCE_RESPONSE_BYTES + 1)
    if len(payload) > MAX_SOURCE_RESPONSE_BYTES:
        raise ValueError(
            f"Response exceeded max size ({MAX_SOURCE_RESPONSE_BYTES} bytes)."
        )
    return payload


class _NoRedirectHandler(urlrequest.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urlrequest.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


_NO_REDIRECT_OPENER = urlrequest.build_opener(_NoRedirectHandler)


def _request_url(url: str) -> tuple[int | None, str, bytes, str | None]:
    target = _normalize_url(url)
    if not target:
        return None, "", b"", "Empty URL."

    redirects = 0
    while redirects <= MAX_REDIRECTS:
        valid, reason = _validate_fetch_url(target)
        if not valid:
            return None, "", b"", f"Blocked URL for security reasons: {reason}"

        req = urlrequest.Request(target, headers={"User-Agent": USER_AGENT})
        try:
            with _NO_REDIRECT_OPENER.open(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
                status = getattr(resp, "status", None)
                content_type = _str(resp.headers.get("Content-Type"))
                payload = _read_response_payload(resp)
                return status, content_type, payload, None
        except urlerror.HTTPError as exc:
            status = exc.code
            content_type = _str(exc.headers.get("Content-Type") if exc.headers else "")
            if status in REDIRECT_HTTP_CODES:
                location = _str(exc.headers.get("Location") if exc.headers else "")
                if not location:
                    return status, content_type, b"", f"Redirect (HTTP {status}) without Location header."
                target = _normalize_url(urljoin(target, location))
                redirects += 1
                continue
            return status, content_type, b"", f"HTTP {status}"
        except urlerror.URLError as exc:
            return None, "", b"", f"Network error: {exc.reason}"
        except Exception as exc:  # noqa: BLE001
            return None, "", b"", str(exc)

    return None, "", b"", f"Too many redirects (>{MAX_REDIRECTS})."


def _decode_text(content_type: str, payload: bytes) -> str:
    if not payload:
        return ""
    charset = "utf-8"
    match = re.search(r"charset=([^\s;]+)", content_type or "", flags=re.IGNORECASE)
    if match:
        charset = match.group(1).strip().strip('"').strip("'")
    try:
        return payload.decode(charset, errors="replace")
    except Exception:  # noqa: BLE001
        return payload.decode("utf-8", errors="replace")


def _extract_pdf_text(payload: bytes) -> tuple[str, str | None]:
    if not payload:
        return "", "Empty PDF payload."
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(BytesIO(payload))
        chunks: list[str] = []
        for page in reader.pages[:25]:
            text = page.extract_text() or ""
            if text:
                chunks.append(text)
        return "\n".join(chunks), None
    except Exception as exc:  # noqa: BLE001
        return "", f"PDF text extraction unavailable ({exc})."


def _extract_search_result_urls(html_text: str) -> list[str]:
    urls: list[str] = []
    for match in re.findall(r'href="([^"]+)"', html_text, flags=re.IGNORECASE):
        href = unquote(match)
        if "duckduckgo.com/l/?" in href:
            parsed = urlparse(href)
            target = parse_qs(parsed.query).get("uddg", [""])[0]
            if target:
                urls.append(target)
        elif href.startswith("http"):
            urls.append(href)
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        out.append(url)
        if len(out) >= 7:
            break
    return out


def _run_search_queries(org_name: str) -> list[str]:
    results: list[str] = []
    for template in SEARCH_QUERIES:
        query = template.format(name=org_name)
        search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        status, content_type, payload, _error = _request_url(search_url)
        if not payload or (status and status >= 400):
            continue
        html_text = _decode_text(content_type, payload)
        for link in _extract_search_result_urls(html_text):
            if link not in results:
                results.append(link)
        if len(results) >= 8:
            break
    return results


def _build_candidate_urls(org_name: str, organization_website: str, irb_page_url: str) -> list[SourceDoc]:
    sources: list[SourceDoc] = []

    irb_url = _normalize_url(irb_page_url)
    if irb_url:
        sources.append(SourceDoc(url=irb_url, source_type="web"))

    base = _normalize_url(organization_website)
    if base:
        sources.append(SourceDoc(url=base, source_type="web"))
        for path in LIKELY_IRB_PATHS:
            sources.append(SourceDoc(url=urljoin(base.rstrip("/") + "/", path.lstrip("/")), source_type="guessed"))

    if not base and org_name:
        guessed_host = _slugify(org_name).replace("-", "")
        if guessed_host:
            sources.append(SourceDoc(url=f"https://{guessed_host}.edu", source_type="guessed"))
            for path in LIKELY_IRB_PATHS[:3]:
                sources.append(SourceDoc(url=f"https://{guessed_host}.edu{path}", source_type="guessed"))

    should_search = not (irb_url or base)
    if should_search and org_name:
        for link in _run_search_queries(org_name):
            sources.append(SourceDoc(url=link, source_type="search"))

    deduped: list[SourceDoc] = []
    seen: set[str] = set()
    for source in sources:
        if not source.url or source.url in seen:
            continue
        seen.add(source.url)
        deduped.append(source)
    return deduped[:MAX_SOURCE_FETCH]


def _resolve_links(base_url: str, links: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for href in links[:MAX_LINKS_PER_PAGE]:
        absolute = urljoin(base_url, href)
        if not absolute.startswith(("http://", "https://")):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        out.append(absolute)
    return out


def _extract_doc_links(links: list[str]) -> list[str]:
    matches = []
    for link in links:
        lower = link.lower()
        if lower.endswith((".pdf", ".doc", ".docx", ".rtf")):
            matches.append(link)
            continue
        if any(hint in lower for hint in ["consent", "template", "application", "checklist", "protocol"]):
            matches.append(link)
    dedup = []
    seen = set()
    for link in matches:
        if link in seen:
            continue
        seen.add(link)
        dedup.append(link)
    return dedup[:18]


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _rule_hits(text: str) -> dict[str, int]:
    hits: dict[str, int] = {}
    lowered = text.lower()
    for rule in REQUIREMENT_RULES:
        count = 0
        for pattern in rule["patterns"]:
            count += len(re.findall(pattern, lowered, flags=re.IGNORECASE))
        hits[rule["id"]] = count
    return hits


def _rule_highlights(text: str, rule_id: str, max_items: int = 2) -> list[str]:
    rule = next((r for r in REQUIREMENT_RULES if r["id"] == rule_id), None)
    if not rule:
        return []
    sentences = _sentences(text)
    matched: list[str] = []
    for sentence in sentences:
        for pattern in rule["patterns"]:
            if re.search(pattern, sentence, flags=re.IGNORECASE):
                matched.append(sentence)
                break
        if len(matched) >= max_items:
            break
    return matched


def _fetch_source(source: SourceDoc) -> SourceDoc:
    status, content_type, payload, error_text = _request_url(source.url)
    source.http_status = status
    source.content_type = content_type
    if error_text:
        source.status = "failed"
        source.error = error_text
        return source
    if not payload:
        source.status = "failed"
        source.error = "Empty response."
        return source

    content_type_lower = content_type.lower()
    url_lower = source.url.lower()
    if "application/pdf" in content_type_lower or url_lower.endswith(".pdf"):
        text, pdf_error = _extract_pdf_text(payload)
        source.title = source.url.rsplit("/", 1)[-1]
        source.text = text[:MAX_TEXT_CHARS]
        source.links = []
        source.status = "fetched"
        if pdf_error and not source.error:
            source.error = pdf_error
        return source

    html_text = _decode_text(content_type, payload)
    parser = _LinkTextExtractor()
    try:
        parser.feed(html_text)
    except Exception:  # noqa: BLE001
        # Fall back to plain text if HTML parser fails.
        parser = _LinkTextExtractor()
        parser.links = []
        parser._text_chunks = [re.sub(r"<[^>]+>", " ", html_text)]  # noqa: SLF001
    source.title = parser.title or source.url
    source.text = parser.text[:MAX_TEXT_CHARS]
    source.links = _resolve_links(source.url, parser.links)
    source.status = "fetched"
    return source


def _build_imported_profile(
    org_name: str,
    profile_id: str,
    hits_aggregate: dict[str, int],
    source_docs: list[SourceDoc],
    document_links: list[str],
    base_profile: dict[str, Any],
) -> dict[str, Any]:
    profile = deepcopy(base_profile)
    profile["id"] = profile_id
    profile["name"] = f"{org_name} IRB Draft Profile (Imported)"
    profile["shortName"] = f"{org_name} Imported IRB"
    profile["version"] = "importer-v1"
    profile["description"] = (
        f"Draft imported profile for {org_name}. Generated from publicly available IRB/HRPP sources; "
        "requires human verification before use."
    )
    profile["imported"] = True
    profile["importedAt"] = datetime.now(timezone.utc).isoformat()
    profile["sourceLinks"] = [doc.url for doc in source_docs if doc.status == "fetched"][:12]
    profile["sourceDocumentLinks"] = document_links[:18]
    profile["importSignals"] = {key: int(value) for key, value in hits_aggregate.items() if value > 0}

    required_manual = list(profile.get("requiredManualAttachments", []))
    recommended_manual = list(profile.get("recommendedManualAttachments", []))

    def ensure_required(attachment_id: str, label: str, reason: str) -> None:
        if any(_str(item.get("id")) == attachment_id for item in required_manual):
            return
        required_manual.append({"id": attachment_id, "label": label, "reason": reason})

    def ensure_recommended(attachment_id: str, label: str, reason: str) -> None:
        if any(_str(item.get("id")) == attachment_id for item in recommended_manual):
            return
        recommended_manual.append({"id": attachment_id, "label": label, "reason": reason})

    if hits_aggregate.get("consent_template", 0) > 0:
        ensure_required(
            "institution_consent_template_check",
            "Institution Consent Template Alignment",
            "Source pages mention consent templates/process requirements; align consent draft to local template language.",
        )
    if hits_aggregate.get("training", 0) > 0:
        ensure_required(
            "research_training_documentation",
            "Human Subjects Training Proof",
            "Source pages mention required research ethics training (e.g., CITI).",
        )
    if hits_aggregate.get("recruitment_materials", 0) > 0:
        ensure_required(
            "recruitment_materials_copy",
            "Recruitment Materials Copy",
            "Source pages mention recruitment material review.",
        )
    if hits_aggregate.get("hipaa_health_data", 0) > 0:
        ensure_recommended(
            "hipaa_screening_note",
            "HIPAA / PHI Applicability Note",
            "Source pages reference HIPAA/PHI; confirm whether health-data rules apply to your protocol.",
        )

    if document_links:
        ensure_recommended(
            "imported_form_link_review",
            "Imported IRB Form/Template Link Review",
            "Importer found possible IRB form/template links. Validate versions before submission.",
        )

    profile["requiredManualAttachments"] = required_manual
    profile["recommendedManualAttachments"] = recommended_manual

    return profile


def import_irb_profile(
    org_name: str,
    organization_website: str = "",
    irb_page_url: str = "",
    raw_policy_text: str = "",
    profile_id: str = "",
    base_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    org_name = _str(org_name)
    if not org_name:
        raise ValueError("organizationName is required.")

    base_profile = deepcopy(base_profile or {})
    candidate_sources = _build_candidate_urls(org_name, organization_website, irb_page_url)
    if raw_policy_text.strip():
        candidate_sources.insert(
            0,
            SourceDoc(
                url="inline://raw_policy_text",
                source_type="inline_text",
                status="fetched",
                content_type="text/plain",
                title=f"{org_name} (Pasted Policy Text)",
                text=raw_policy_text[:MAX_TEXT_CHARS],
                links=[],
            ),
        )

    fetched_sources: list[SourceDoc] = []
    for source in candidate_sources:
        if source.source_type == "inline_text":
            fetched_sources.append(source)
            continue
        fetched_sources.append(_fetch_source(source))

    # Collect second-level document links from fetched pages and parse a few PDFs for stronger signals.
    discovered_doc_links: list[str] = []
    for source in fetched_sources:
        if source.status != "fetched":
            continue
        discovered_doc_links.extend(_extract_doc_links(source.links or []))
    dedup_doc_links: list[str] = []
    seen_docs: set[str] = set()
    for link in discovered_doc_links:
        if link in seen_docs:
            continue
        seen_docs.add(link)
        dedup_doc_links.append(link)

    pdf_parse_attempts = 0
    for link in dedup_doc_links:
        if pdf_parse_attempts >= MAX_PDF_SOURCES_TO_PARSE:
            break
        if not link.lower().endswith(".pdf"):
            continue
        source = _fetch_source(SourceDoc(url=link, source_type="web"))
        fetched_sources.append(source)
        pdf_parse_attempts += 1

    hits_aggregate = {rule["id"]: 0 for rule in REQUIREMENT_RULES}
    rule_highlights: dict[str, list[str]] = {rule["id"]: [] for rule in REQUIREMENT_RULES}
    source_metadata: list[dict[str, Any]] = []

    for source in fetched_sources:
        text = (source.text or "")[:MAX_TEXT_CHARS]
        hits = _rule_hits(text) if text else {rule["id"]: 0 for rule in REQUIREMENT_RULES}
        for rule_id, count in hits.items():
            hits_aggregate[rule_id] += count
            if count > 0 and len(rule_highlights[rule_id]) < 3:
                for sentence in _rule_highlights(text, rule_id, max_items=2):
                    if sentence not in rule_highlights[rule_id]:
                        rule_highlights[rule_id].append(sentence)
                    if len(rule_highlights[rule_id]) >= 3:
                        break
        source_metadata.append(source.as_metadata(hits))

    signal_summaries: list[dict[str, Any]] = []
    for rule in REQUIREMENT_RULES:
        count = hits_aggregate[rule["id"]]
        if count <= 0:
            continue
        signal_summaries.append(
            {
                "id": rule["id"],
                "label": rule["label"],
                "evidenceCount": count,
                "summary": rule["summary"],
                "highlights": rule_highlights[rule["id"]][:3],
            }
        )

    if not profile_id:
        profile_id = f"imported_{_slugify(org_name)}_v1"

    imported_profile = _build_imported_profile(
        org_name=org_name,
        profile_id=profile_id,
        hits_aggregate=hits_aggregate,
        source_docs=fetched_sources,
        document_links=dedup_doc_links,
        base_profile=base_profile,
    )

    fetched_count = sum(1 for src in fetched_sources if src.status == "fetched")
    failed_count = sum(1 for src in fetched_sources if src.status == "failed")
    weight_score = sum(
        rule["weight"] for rule in REQUIREMENT_RULES if hits_aggregate[rule["id"]] > 0
    )
    confidence = 0.22
    if fetched_count > 0:
        confidence += 0.24
    if signal_summaries:
        confidence += min(0.42, weight_score)
    if failed_count > fetched_count:
        confidence -= 0.08
    if not signal_summaries:
        confidence -= 0.05
    confidence = max(0.08, min(0.93, confidence))

    warnings: list[str] = []
    if fetched_count == 0:
        warnings.append("No source pages were successfully fetched. Draft profile uses fallback assumptions.")
    if failed_count > 0:
        warnings.append(f"{failed_count} source requests failed; requirements may be incomplete.")
    if not signal_summaries:
        warnings.append("No strong requirement signals detected from sources; verify manually.")

    if dedup_doc_links:
        warnings.append("Document links were detected but may not be the latest official form versions.")

    warnings.append(
        "Imported profile is a best-effort draft and must be validated against your institution's official IRB office instructions."
    )

    notes = [
        "Importer searches public IRB/HRPP pages and extracts requirement signals via keyword heuristics.",
        "Use source links and highlights as verification starting points before relying on the generated profile.",
    ]

    return {
        "organizationName": org_name,
        "profileDraft": imported_profile,
        "confidence": round(confidence, 2),
        "warnings": warnings,
        "notes": notes,
        "sources": source_metadata,
        "signals": signal_summaries,
        "documentLinks": dedup_doc_links[:18],
        "stats": {
            "candidateSourceCount": len(candidate_sources),
            "fetchedSourceCount": fetched_count,
            "failedSourceCount": failed_count,
            "signalCount": len(signal_summaries),
        },
        "debug": {
            "requestContext": {
                "organizationWebsite": _normalize_url(organization_website),
                "irbPageUrl": _normalize_url(irb_page_url),
                "usedRawPolicyText": bool(raw_policy_text.strip()),
            },
            "signalHits": hits_aggregate,
        },
    }


if __name__ == "__main__":
    # Simple local smoke usage:
    payload = import_irb_profile(
        org_name="Example University",
        raw_policy_text=(
            "The Institutional Review Board reviews exempt, expedited, and full board studies. "
            "Researchers must complete CITI training and submit consent forms and recruitment scripts."
        ),
        base_profile={},
    )
    print(json.dumps(payload, indent=2))
