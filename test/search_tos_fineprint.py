"""FinePrint 약관·정책 문서 수집기

기능
1. 서비스명으로 이용약관, 개인정보 처리방침, 환불·해지 정책,
   자동결제 정책 후보를 검색합니다.
2. 허용된 공식 도메인과 최종 리디렉션 주소를 검증해 기사·블로그를 차단합니다.
3. 현재 공식 페이지에서 개정일을 추출하고, 이용약관은 개정일이 있을 때만 저장합니다.
4. 웹 페이지, PDF, TXT를 텍스트로 변환해 검증된 이용약관 원문만 저장합니다.

이 파일은 FinePrint의 "문서 탐색·인입·전처리" 단계입니다.

필요 패키지
    pip install tavily-python requests PyPDF2 python-dotenv
선택 패키지(본문 추출 품질 향상)
    pip install pymupdf trafilatura playwright
    python -m playwright install chromium

실행 예시
    python search_tos_fineprint.py
    python search_tos_fineprint.py --service "넷플릭스"
    python search_tos_fineprint.py --service "다른 서비스"
"""

from __future__ import annotations

import argparse
import hashlib
from html import unescape
import logging
import os
import re
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

try:
    import requests
except ImportError:  # 웹 검색/HTML 수집을 사용하지 않는 로컬 인입에는 불필요하다.
    requests = None

try:
    from PyPDF2 import PdfReader
except ImportError:
    try:
        from pypdf import PdfReader
    except ImportError:
        PdfReader = None
try:
    from tavily import TavilyClient
except ImportError:  # 직접 PDF/TXT만 처리할 때는 Tavily가 없어도 된다.
    TavilyClient = None

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv는 선택 사항
    load_dotenv = None

try:
    import fitz  # PyMuPDF: 스캔/PDF 본문 추출용
except ImportError:
    fitz = None

try:
    import trafilatura  # 웹 본문 추출용
except ImportError:
    trafilatura = None

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


APP_NAME = "FinePrint"
DEFAULT_MAX_RESULTS = 8
DEFAULT_CHUNK_SIZE = 1400
DEFAULT_CHUNK_OVERLAP = 220
USER_AGENT = (
    "Mozilla/5.0 (FinePrint document collector; +https://example.invalid)"
)

# 검색 대상 문서 유형. 신청서에 적힌 문제 유형과 직접 연결된다.
DOCUMENT_QUERY_TEMPLATES: dict[str, tuple[str, ...]] = {
    "terms": (
        "{service} 이용약관",
        "{service} 서비스 약관",
        "{service} terms of service",
    ),
    "privacy": (
        "{service} 개인정보 처리방침",
        "{service} privacy policy",
    ),
    "refund_cancellation": (
        "{service} 환불 해지 정책",
        "{service} 환불정책 이용 해지",
        "{service} refund cancellation policy",
    ),
    "billing_autorenewal": (
        "{service} 자동결제 정기결제 정책",
        "{service} 결제 갱신 해지",
        "{service} billing auto renewal policy",
    ),
    # 신청서의 "앱스토어·구글플레이 결제 환불 절차" 요구사항을 위한 유형.
    "platform_refund": (
        "{service} 앱스토어 환불",
        "{service} 구글플레이 환불",
        "{service} App Store Google Play refund",
    ),
}

DOCUMENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "terms": (
        "이용약관", "서비스 약관", "약관", "terms", "terms-of-service",
        "terms of service", "terms and conditions",
    ),
    "privacy": (
        "개인정보", "개인정보 처리방침", "privacy", "personal information",
    ),
    "refund_cancellation": (
        "환불", "해지", "취소", "refund", "cancellation", "terminate",
    ),
    "billing_autorenewal": (
        "자동결제", "정기결제", "결제", "갱신", "billing", "auto-renew",
        "renewal", "recurring",
    ),
    "platform_refund": (
        "앱스토어", "구글플레이", "app store", "google play", "refund",
        "환불",
    ),
}

# 뉴스/블로그/약관 집계 사이트는 공식 문서 후보에서 제외한다.
BLACKLISTED_HOST_PARTS = (
    "blog.naver.com", "tistory.com", "brunch.co.kr", "medium.com",
    "wordpress.com", "wikipedia.org", "reddit.com", "joongang.co.kr",
    "koreajoongangdaily.com", "hankyung.com", "chosun.com", "hani.co.kr",
    "news.naver.com", "terms-watchdog", "toswatchdog", "terms.law",
)

# 앱스토어 앱 상세 페이지는 약관이 아니며, 공식 고객지원 환불 문서만 허용한다.
PLATFORM_POLICY_DOMAINS = ("support.apple.com", "support.google.com")

# 이름에 브랜드가 포함된 가짜 도메인을 막기 위해, 확정된 서비스는 루트 도메인을 명시한다.
OFFICIAL_DOMAIN_OVERRIDES: dict[str, tuple[str, ...]] = {
    "netflix": ("netflix.com",),
    "넷플릭스": ("netflix.com",),
    "tving": ("tving.com",),
    "티빙": ("tving.com",),
    # 코웨이는 쇼핑몰·협력사 도메인이 많이 함께 검색되므로 본사 도메인만 먼저 허용한다.
    "coway": ("coway.com",),
    "코웨이": ("coway.com",),
}

# 검색 캐시가 아닌 현재 공식 법률 페이지를 먼저 직접 수집할 수 있는 서비스별 기준 URL.
OFFICIAL_POLICY_URLS: dict[str, dict[str, str]] = {
    "netflix": {
        "terms": "https://help.netflix.com/ko/legal/termsofuse",
    },
    "넷플릭스": {
        "terms": "https://help.netflix.com/ko/legal/termsofuse",
    },
    "tving": {
        "terms": "https://www.tving.com/policy/terms",
    },
    "티빙": {
        "terms": "https://www.tving.com/policy/terms",
    },
}

# 자동 도메인 탐색에서 기사/보도자료 URL을 후보로 쓰지 않기 위한 경로·호스트 신호.
DISCOVERY_NEWS_SIGNALS = (
    "/news/", "/article/", "/articles/", "/press/", "/media/", "/view/",
    "news.", "press.", "newsis", "yna.co.kr",
)
DISCOVERY_BLOCKED_DOMAINS = (
    "instagram.com", "facebook.com", "threads.net", "x.com", "twitter.com",
    "youtube.com", "tiktok.com", "linkedin.com", "pinterest.com", "naver.com",
    "daum.net", "google.com", "bing.com",
    "wikipedia.org", "namu.wiki", "reddit.com", "quora.com", "blogspot.com",
    "medium.com", "brunch.co.kr", "velog.io", "notion.site", "apps.apple.com",
    "play.google.com",
)
MULTI_LABEL_PUBLIC_SUFFIXES = {"co.kr", "or.kr", "go.kr", "com.au", "co.jp", "co.uk"}


@dataclass
class Candidate:
    """검색 결과 1건과 점수 계산 결과."""

    url: str
    title: str
    snippet: str
    requested_type: str
    detected_type: str
    score: int = 0
    official_domain: bool = False
    canonical_source: bool = False
    reasons: tuple[str, ...] = ()
    # 자동 탐색 단계에서 실제 본문까지 검증한 결과를 보관한다. 같은 페이지를 다시 받지 않는다.
    validated_text: str = ""
    validated_source_kind: str = ""
    validated_final_url: str = ""


@dataclass
class CollectedDocument:
    """RAG 입력으로 저장할 문서 구조."""

    service_name: str
    document_type: str
    title: str
    source_url: str
    source_kind: str
    official_domain: bool
    revision_date: str | None
    selection_score: int
    collected_at: str
    sha256: str
    text: str
    chunks: list[str]


def configure_logging(base_dir: Path) -> None:
    """수집 과정과 실패 원인을 logs/extract.log에 기록한다."""
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_dir / "extract.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def normalize_text(text: str) -> str:
    """줄바꿈·공백을 정리해 검색과 청킹 품질을 높인다."""
    text = text.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_url(url: str) -> str:
    """추적용 query parameter를 제거해 같은 페이지의 중복을 줄인다."""
    parsed = urlparse(url)
    ignored = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}
    query = urlencode(
        [(key, value) for key, value in parse_qsl(parsed.query) if key not in ignored]
    )
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path, "", query, ""))


def safe_service_name(service_name: str) -> str:
    """서비스명을 파일 시스템에 안전한 폴더명으로 변환한다."""
    name = unicodedata.normalize("NFKC", service_name).strip().lower()
    name = re.sub(r"[^0-9a-z가-힣_-]+", "_", name)
    return name.strip("_.")[:100] or "untitled"


def service_key(service_name: str) -> str:
    """서비스 별칭 비교에 사용할 정규화 키를 만든다."""
    return re.sub(r"[^0-9a-z가-힣]", "", service_name.lower())


def normalize_domain(domain: str) -> str:
    """URL 또는 도메인 입력값을 루트 도메인 비교용 값으로 정리한다."""
    candidate = domain.strip().lower()
    if "://" in candidate:
        candidate = urlparse(candidate).netloc
    return candidate.split("/")[0].removeprefix("www.")


def domain_matches(host: str, allowed_domain: str) -> bool:
    """허용 도메인과 그 하위 도메인만 일치로 인정한다."""
    host = host.lower().split(":")[0]
    allowed_domain = normalize_domain(allowed_domain)
    return host == allowed_domain or host.endswith("." + allowed_domain)


def resolve_official_domains(service_name: str, supplied_domains: list[str]) -> tuple[str, ...]:
    """명시 입력값 또는 검증된 서비스별 기본 도메인을 반환한다."""
    domains = [normalize_domain(domain) for domain in supplied_domains if normalize_domain(domain)]
    if not domains:
        domains = list(OFFICIAL_DOMAIN_OVERRIDES.get(service_key(service_name), ()))
    return tuple(dict.fromkeys(domains))


def allowed_domains_for_type(document_type: str, service_domains: tuple[str, ...]) -> tuple[str, ...]:
    """플랫폼 환불 문서에는 Apple/Google 고객지원 도메인도 별도로 허용한다."""
    if document_type == "platform_refund":
        return service_domains + PLATFORM_POLICY_DOMAINS
    return service_domains


def is_official_url(url: str, allowed_domains: tuple[str, ...]) -> bool:
    """URL이 사용자가 승인했거나 등록된 공식 도메인에 속하는지 확인한다."""
    host = urlparse(url).netloc.lower()
    return bool(host and any(domain_matches(host, domain) for domain in allowed_domains))


def registrable_domain(host: str) -> str:
    """서브도메인을 제거한 등록 가능 도메인을 근사 계산한다."""
    labels = host.lower().split(":")[0].split(".")
    if len(labels) < 2:
        return host.lower()
    last_two = ".".join(labels[-2:])
    if last_two in MULTI_LABEL_PUBLIC_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return last_two


def looks_like_news_url(url: str) -> bool:
    """공식 홈페이지 탐색 시 기사·보도자료 URL을 후보에서 제거한다."""
    normalized = url.lower()
    return any(signal in normalized for signal in DISCOVERY_NEWS_SIGNALS)


def is_blocked_discovery_domain(url: str) -> bool:
    """소셜 미디어·검색 포털은 브랜드를 언급해도 공식 홈페이지 후보가 될 수 없다."""
    host = urlparse(url).netloc.lower()
    return any(domain_matches(host, domain) for domain in DISCOVERY_BLOCKED_DOMAINS)


def is_home_or_policy_url(url: str) -> bool:
    """자동 탐색에서는 홈페이지 또는 약관 경로만 채택해 게시물/프로필을 배제한다."""
    path_parts = [part for part in urlparse(url).path.lower().split("/") if part]
    if not path_parts:
        return True
    if len(path_parts) == 1 and re.fullmatch(r"[a-z]{2}(?:-[a-z]{2})?", path_parts[0]):
        return True
    policy_parts = {"policy", "legal", "terms", "termsofuse", "privacy", "agreement"}
    return any(part in policy_parts for part in path_parts)


def discover_official_domains(client: TavilyClient, service_name: str) -> tuple[str, ...]:
    """서비스명으로 공식 홈페이지 후보를 찾아 높은 신뢰도일 때만 도메인을 채택한다.

    검색 결과만으로 공식성을 완전히 증명할 수 없으므로, 기사·블로그·뉴스 URL을 제외하고
    서비스명/공식 표기/도메인 일치 신호가 충분한 경우에만 반환한다. 불확실하면 빈 값이다.
    """
    queries = (f"{service_name} 공식 홈페이지", f"{service_name} official site")
    best_domain = ""
    best_score = -1
    service_identity = service_key(service_name)

    for query in queries:
        try:
            results = client.search(
                query=query,
                search_depth="advanced",
                max_results=8,
                include_raw_content=False,
            ).get("results", [])
        except Exception:
            logging.exception("Official-domain discovery failed: %s", query)
            continue

        for index, result in enumerate(results):
            url = normalize_url(result.get("url", ""))
            if not url.startswith(("https://", "http://")):
                continue
            if (
                is_blacklisted(url)
                or looks_like_news_url(url)
                or is_blocked_discovery_domain(url)
                or not is_home_or_policy_url(url)
            ):
                continue

            title = (result.get("title") or "").lower()
            snippet = (result.get("content") or "").lower()
            host = urlparse(url).netloc.lower()
            domain = registrable_domain(host)
            compact_domain = re.sub(r"[^0-9a-z가-힣]", "", domain)
            compact_title = re.sub(r"[^0-9a-z가-힣]", "", title)
            compact_snippet = re.sub(r"[^0-9a-z가-힣]", "", snippet)

            score = max(0, 24 - index * 3)  # 검색 상위 결과만 보조 신호로 활용
            if service_identity and service_identity in compact_domain:
                score += 70
            if service_identity and (
                service_identity in compact_title or service_identity in compact_snippet
            ):
                score += 30
            if any(word in title for word in ("official", "공식 홈페이지", "공식 사이트")):
                score += 25
            if urlparse(url).path in ("", "/"):
                score += 10

            if score > best_score:
                best_domain, best_score = domain, score

    if best_score >= 60:
        logging.info("Discovered official domain for %s: %s (%s)", service_name, best_domain, best_score)
        return (best_domain,)
    logging.warning("Could not confidently discover official domain for %s", service_name)
    return ()


def load_tavily_client() -> TavilyClient:
    """환경변수에서 Tavily 키를 읽고 검색 클라이언트를 만든다."""
    if TavilyClient is None:
        raise RuntimeError("tavily-python이 설치되어 있지 않습니다.")
    if load_dotenv:
        load_dotenv()
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError(
            "TAVILY_API_KEY가 없습니다. .env 또는 환경변수에 검색 API 키를 설정하세요."
        )
    return TavilyClient(api_key=api_key)


def is_blacklisted(url: str) -> bool:
    """공식 문서 후보로 부적절한 뉴스·블로그·집계 호스트인지 확인한다."""
    host = urlparse(url).netloc.lower()
    return any(part in host for part in BLACKLISTED_HOST_PARTS)


def looks_like_news_article(text: str) -> bool:
    """약관 키워드를 인용한 뉴스 기사를 보수적으로 차단한다."""
    sample = text[:5000].lower()
    news_signals = (
        "기자", "국회", "의원", "보도", "취재", "연합뉴스", "신문",
        "뉴스", "기사", "입력", "발행", "특파원",
    )
    clause_signal = bool(re.search(r"제\s*\d+\s*조|article\s+\d+|section\s+\d+", sample))
    return sum(signal in sample for signal in news_signals) >= 2 and not clause_signal


def extract_revision_date(text: str) -> str | None:
    """공식 페이지에 표시된 최종 개정일을 추출한다."""
    patterns = (
        r"(?:last\s+updated|last\s+modified|updated|최종\s*업데이트|마지막\s*업데이트|시행일)\s*[:：]?\s*([^\n]{3,80})",
        r"(?:개정일|업데이트일)\s*[:：]?\s*([^\n]{3,80})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(" .:-")
    return None


def has_current_terms_marker(text: str) -> bool:
    """개정일 대신 공식 페이지가 현행 약관임을 명시하는 경우를 확인한다."""
    sample = text[:12000].lower()
    return (
        ("현행" in sample and "이용약관" in sample)
        or "current terms" in sample
        or "current terms of use" in sample
    )


def service_tokens(service_name: str) -> list[str]:
    """서비스명에서 도메인 관련성 확인용 토큰을 만든다."""
    return [
        token for token in re.split(r"[^0-9a-zA-Z가-힣]+", service_name.lower())
        if len(token) >= 2
    ]


def is_related_domain(url: str, service_name: str) -> bool:
    """서비스명이 도메인에 포함되는지 확인한다. 검색 결과의 보조 신호다."""
    host = urlparse(url).netloc.lower()
    compact_name = re.sub(r"[^0-9a-z가-힣]", "", service_name.lower())
    compact_host = re.sub(r"[^0-9a-z가-힣]", "", host)
    return bool(compact_name and compact_name in compact_host) or any(
        token in compact_host for token in service_tokens(service_name)
    )


def classify_document_type(url: str, title: str, snippet: str, requested_type: str) -> str:
    """URL·제목·검색 요약을 이용해 실제 문서 유형을 분류한다."""
    haystack = f"{url} {title} {snippet}".lower()
    scores = {
        kind: sum(1 for keyword in keywords if keyword.lower() in haystack)
        for kind, keywords in DOCUMENT_KEYWORDS.items()
    }
    scores[requested_type] += 2
    return max(scores, key=scores.get)


def url_has_document_keyword(url: str, document_type: str) -> bool:
    """URL 경로에 해당 문서 유형의 명확한 키워드가 있는지 확인한다."""
    path = urlparse(url).path.lower()
    return any(keyword.lower() in path for keyword in DOCUMENT_KEYWORDS[document_type])


def content_looks_like_policy(text: str, document_type: str | None = None) -> bool:
    """짧은 뉴스/홈페이지가 아니라 정책 문서처럼 보이는지 보수적으로 판단한다."""
    if not text:
        return False
    sample = text[:12000].lower()
    clause_signal = bool(re.search(r"제\s*\d+\s*조|article\s+\d+|section\s+\d+", sample))
    numbered_section_count = len(re.findall(
        r"(?m)^\s*(?:제\s*\d+\s*조|\d+(?:\.\d+){0,2}\.\s+\S)", sample
    ))
    policy_signal = any(
        phrase in sample
        for phrase in (
            "이용약관", "개인정보 처리방침", "환불", "해지", "자동결제",
            "terms of service", "privacy policy", "refund policy",
        )
    )
    type_signal = bool(document_type and any(
        keyword.lower() in sample for keyword in DOCUMENT_KEYWORDS[document_type]
    ))
    # 이용약관은 메뉴/정책 허브 문구만으로 통과시키지 않는다. 실제 조항 구조가 있어야 한다.
    if document_type == "terms":
        return type_signal and (clause_signal or numbered_section_count >= 4)
    return clause_signal or (policy_signal and type_signal)


def score_candidate(
    service_name: str,
    candidate: Candidate,
    allowed_domains: tuple[str, ...],
) -> Candidate:
    """공식성·문서성·문서 유형 일치도를 합산해 후보를 정렬한다."""
    url = candidate.url
    score = 0
    reasons: list[str] = []
    official = is_official_url(url, allowed_domains)

    if official:
        score += 120
        reasons.append("official-domain:+120")
    else:
        score -= 1000
        reasons.append("unapproved-domain:-1000")
    if candidate.canonical_source:
        score += 1000
        reasons.append("canonical-source:+1000")
    if url_has_document_keyword(url, candidate.requested_type):
        score += 50
        reasons.append("document-path:+50")
    if candidate.detected_type == candidate.requested_type:
        score += 30
        reasons.append("document-type:+30")
    if any(keyword.lower() in candidate.title.lower() for keyword in DOCUMENT_KEYWORDS[candidate.requested_type]):
        score += 20
        reasons.append("title-keyword:+20")
    if candidate.snippet and content_looks_like_policy(candidate.snippet, candidate.requested_type):
        score += 35
        reasons.append("policy-snippet:+35")
    if urlparse(url).path in ("", "/"):
        score -= 25
        reasons.append("root-page:-25")

    candidate.score = score
    candidate.official_domain = official and not is_blacklisted(url)
    candidate.reasons = tuple(reasons)
    return candidate


def search_policy_documents(
    client: TavilyClient,
    service_name: str,
    service_domains: tuple[str, ...],
    max_results: int = DEFAULT_MAX_RESULTS,
) -> list[Candidate]:
    """신청서에 명시된 문서 유형별로 Tavily 검색을 실행하고 중복을 제거한다."""
    candidates: dict[str, Candidate] = {}
    for requested_type, templates in DOCUMENT_QUERY_TEMPLATES.items():
        for template in templates:
            query = template.format(service=service_name)
            logging.info("Searching %s: %s", requested_type, query)
            try:
                response = client.search(
                    query=query,
                    search_depth="advanced",
                    max_results=max_results,
                    include_raw_content=False,
                )
            except Exception:
                logging.exception("Tavily search failed: %s", query)
                continue

            for result in response.get("results", []):
                url = normalize_url(result.get("url", ""))
                if not url.startswith(("http://", "https://")):
                    continue
                if is_blacklisted(url):
                    logging.info("Skipping blacklisted search result: %s", url)
                    continue
                allowed_domains = allowed_domains_for_type(requested_type, service_domains)
                if not is_official_url(url, allowed_domains):
                    logging.info("Skipping non-official search result: %s", url)
                    continue
                title = (result.get("title") or "").strip()
                snippet = (result.get("content") or "").strip()
                detected_type = classify_document_type(url, title, snippet, requested_type)
                item = Candidate(
                    url=url,
                    title=title,
                    snippet=snippet,
                    requested_type=requested_type,
                    detected_type=detected_type,
                )
                item = score_candidate(service_name, item, allowed_domains)
                # 같은 URL이 여러 유형으로 검색되면 더 높은 점수/더 구체적인 유형을 보존한다.
                previous = candidates.get(url)
                if previous is None or item.score > previous.score:
                    candidates[url] = item

    return sorted(candidates.values(), key=lambda item: item.score, reverse=True)


def search_alternate_terms_candidates(
    client: TavilyClient,
    service_name: str,
    service_domains: tuple[str, ...],
    excluded_urls: set[str],
) -> list[Candidate]:
    """사용자 제공 URL의 본문 추출이 실패할 때 같은 공식 도메인의 약관 URL을 다시 찾는다."""
    query = (
        f"site:{service_domains[0]} 이용약관 OR terms of use OR subscriber agreement"
    )
    try:
        results = client.search(
            query=query,
            search_depth="advanced",
            max_results=10,
            include_raw_content=False,
        ).get("results", [])
    except Exception:
        logging.exception("Alternate terms search failed: %s", query)
        return []

    candidates: list[Candidate] = []
    for result in results:
        url = normalize_url(result.get("url", ""))
        if (
            not url.startswith(("http://", "https://"))
            or url in excluded_urls
            or is_blacklisted(url)
            or looks_like_news_url(url)
            or not is_official_url(url, service_domains)
        ):
            continue
        title = (result.get("title") or "").strip()
        snippet = (result.get("content") or "").strip()
        evidence = f"{url} {title} {snippet}".lower()
        if not any(keyword.lower() in evidence for keyword in DOCUMENT_KEYWORDS["terms"]):
            continue
        candidate = Candidate(
            url=url,
            title=title,
            snippet=snippet,
            requested_type="terms",
            detected_type="terms",
        )
        candidates.append(score_candidate(service_name, candidate, service_domains))
    return sorted(candidates, key=lambda item: item.score, reverse=True)


def canonical_policy_candidates(service_name: str, service_domains: tuple[str, ...]) -> list[Candidate]:
    """등록된 공식 법률 URL을 검색 결과보다 우선하는 후보로 추가한다."""
    candidates: list[Candidate] = []
    for document_type, url in OFFICIAL_POLICY_URLS.get(service_key(service_name), {}).items():
        if not is_official_url(url, allowed_domains_for_type(document_type, service_domains)):
            continue
        candidate = Candidate(
            url=normalize_url(url),
            title=f"{service_name} 공식 {document_type}",
            snippet="",
            requested_type=document_type,
            detected_type=document_type,
            canonical_source=True,
        )
        candidates.append(
            score_candidate(
                service_name,
                candidate,
                allowed_domains_for_type(document_type, service_domains),
            )
        )
    return candidates


def extract_pdf_text(path: Path) -> str:
    """PyMuPDF를 우선 사용하고 실패하면 PyPDF2로 PDF 텍스트를 추출한다."""
    if fitz:
        try:
            with fitz.open(path) as document:
                text = "\n\n".join(page.get_text() for page in document)
            if text.strip():
                return normalize_text(text)
        except Exception:
            logging.exception("PyMuPDF extraction failed: %s", path)

    if PdfReader is None:
        raise RuntimeError("PDF 처리를 위해 pymupdf 또는 PyPDF2를 설치하세요.")
    reader = PdfReader(str(path))
    return normalize_text("\n\n".join(page.extract_text() or "" for page in reader.pages))


def extract_local_document(path_value: str) -> tuple[str, str]:
    """사용자가 지정한 PDF/TXT를 읽고 (본문, 파일 유형)을 반환한다."""
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"문서 파일을 찾을 수 없습니다: {path}")
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_text(path), "local_pdf"
    if suffix in {".txt", ".md"}:
        return normalize_text(path.read_text(encoding="utf-8")), "local_text"
    raise ValueError("지원하는 문서 형식은 PDF, TXT, MD입니다.")


def extract_pdf_bytes(data: bytes) -> str:
    """웹에서 내려받은 PDF 바이트를 임시 파일 없이 추출한다."""
    if fitz:
        try:
            with fitz.open(stream=data, filetype="pdf") as document:
                text = "\n\n".join(page.get_text() for page in document)
            if text.strip():
                return normalize_text(text)
        except Exception:
            logging.exception("PyMuPDF byte extraction failed")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
        handle.write(data)
        temp_path = Path(handle.name)
    try:
        return extract_pdf_text(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)


def extract_html_fallback(html: str) -> str:
    """전용 본문 추출기가 없을 때 공식 페이지의 기본 텍스트를 추출한다."""
    without_noncontent = re.sub(
        r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL
    )
    return normalize_text(unescape(re.sub(r"<[^>]+>", " ", without_noncontent)))


def render_page_text(url: str) -> tuple[str, str]:
    """JavaScript 렌더링 페이지의 본문과 최종 리디렉션 URL을 가져온다."""
    if sync_playwright is None:
        return "", url
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1200)
            return normalize_text(page.inner_text("body")), normalize_url(page.url)
        finally:
            browser.close()


def extract_web_document(url: str) -> tuple[str, str, str]:
    """웹 페이지/PDF의 본문·유형·최종 리디렉션 URL을 반환한다."""
    if requests is None:
        logging.warning("requests is not installed; skipping direct web extraction")
        try:
            text, final_url = render_page_text(url)
            return text, "web_rendered_html" if text else "web_unknown", final_url
        except Exception:
            logging.exception("Playwright extraction failed: %s", url)
            return "", "web_unknown", url
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        final_url = normalize_url(response.url)
        content_type = response.headers.get("content-type", "").lower()
        if final_url.lower().endswith(".pdf") or "application/pdf" in content_type:
            text = extract_pdf_bytes(response.content)
            return text, "web_pdf", final_url

        html = response.text
        if trafilatura:
            text = trafilatura.extract(html, include_comments=False, include_tables=True) or ""
            if len(text) >= 500:
                # 본문 추출기가 페이지 하단 개정일을 생략하는 경우를 보완한다.
                html_as_text = re.sub(r"<[^>]+>", " ", html)
                revision_date = extract_revision_date(html_as_text)
                if revision_date and not extract_revision_date(text):
                    text = f"{text}\n\nLast Updated: {revision_date}"
                return normalize_text(text), "web_html", final_url

        fallback_text = extract_html_fallback(html)
        if len(fallback_text) >= 500:
            return fallback_text, "web_html_fallback", final_url
    except Exception:
        logging.exception("Direct web extraction failed: %s", url)

    try:
        text, final_url = render_page_text(url)
        if text:
            return text, "web_rendered_html", final_url
    except Exception:
        logging.exception("Playwright extraction failed: %s", url)
    return "", "web_unknown", url


def extract_tavily_document(client: TavilyClient, url: str) -> tuple[str, str, str]:
    """직접 HTTP/브라우저 추출이 비어 있을 때 Tavily 본문 추출을 보조 수단으로 사용한다."""
    try:
        response = client.extract(urls=[url])
        results = response.get("results", [])
        if not results:
            return "", "tavily_unknown", url
        result = results[0]
        text = normalize_text(result.get("raw_content") or result.get("content") or "")
        final_url = normalize_url(result.get("url") or url)
        return text, "tavily_extract", final_url
    except Exception:
        logging.exception("Tavily extract failed: %s", url)
        return "", "tavily_unknown", url


SERVICE_NAME_ALIASES: dict[str, tuple[str, ...]] = {
    "넷플릭스": ("netflix",),
    "tving": ("티빙",),
    "티빙": ("tving",),
    "coway": ("코웨이",),
    "코웨이": ("coway",),
}


def compact_text(text: str) -> str:
    """대소문자·공백·기호 차이를 무시한 서비스명 비교용 문자열을 만든다."""
    return re.sub(r"[^0-9a-z가-힣]", "", unicodedata.normalize("NFKC", text).lower())


def document_mentions_service(service_name: str, title: str, text: str) -> bool:
    """문서의 제목 또는 초반 본문에 서비스명이 실제로 표시되는지 확인한다."""
    sample = compact_text(f"{title}\n{text[:12000]}")
    identities = [compact_text(service_name)]
    identities.extend(compact_text(alias) for alias in SERVICE_NAME_ALIASES.get(service_key(service_name), ()))
    return any(len(identity) >= 2 and identity in sample for identity in identities)


def is_safe_terms_candidate_url(url: str) -> bool:
    """뉴스·SNS·포털·블로그 등 약관 원문 출처로 쓸 수 없는 URL을 일괄 차단한다."""
    return (
        url.startswith(("http://", "https://"))
        and not is_blacklisted(url)
        and not is_blocked_discovery_domain(url)
        and not looks_like_news_url(url)
    )


def verify_terms_candidate(
    service_name: str,
    candidate: Candidate,
    allowed_domains: tuple[str, ...] = (),
    client: TavilyClient | None = None,
    user_provided: bool = False,
) -> Candidate | None:
    """검색 결과를 바로 믿지 않고, 실제 이용약관 본문을 얻은 뒤에만 후보로 인정한다.

    검증 순서는 URL 안전성 → 최종 리디렉션 도메인 → 약관 조항 구조 → 서비스명 표기다.
    따라서 기사 제목에 서비스명이 들어 있거나 SNS 계정이 '공식'으로 보이는 경우는 통과하지 않는다.
    """
    if not is_safe_terms_candidate_url(candidate.url):
        return None
    if allowed_domains and not is_official_url(candidate.url, allowed_domains):
        return None

    text, source_kind, final_url = extract_web_document(candidate.url)
    if client and (not text or not content_looks_like_policy(text, "terms")):
        tavily_text, tavily_kind, tavily_final_url = extract_tavily_document(client, candidate.url)
        if tavily_text:
            text, source_kind, final_url = tavily_text, tavily_kind, tavily_final_url

    if not is_safe_terms_candidate_url(final_url):
        return None
    effective_domains = allowed_domains or (registrable_domain(urlparse(candidate.url).netloc),)
    if not is_official_url(final_url, effective_domains):
        logging.info("Final URL left the trusted domain: %s -> %s", candidate.url, final_url)
        return None
    if looks_like_news_article(text) or not content_looks_like_policy(text, "terms"):
        return None
    if not user_provided and not document_mentions_service(service_name, candidate.title, text):
        logging.info("Terms text does not identify the requested service: %s", final_url)
        return None

    candidate.url = normalize_url(candidate.url)
    candidate.detected_type = "terms"
    candidate.requested_type = "terms"
    candidate.official_domain = True
    candidate.validated_text = normalize_text(text)
    candidate.validated_source_kind = source_kind
    candidate.validated_final_url = normalize_url(final_url)
    candidate.score = max(candidate.score, 0) + 500
    reasons = list(candidate.reasons)
    reasons.extend(["verified-terms-body:+500", "final-domain:verified"])
    if extract_revision_date(candidate.validated_text) or has_current_terms_marker(candidate.validated_text):
        candidate.score += 40
        reasons.append("current-marker:+40")
    if url_has_document_keyword(candidate.url, "terms"):
        candidate.score += 30
        reasons.append("terms-url:+30")
    candidate.reasons = tuple(dict.fromkeys(reasons))
    return candidate


def search_verified_terms_candidates(
    client: TavilyClient,
    service_name: str,
    trusted_domains: tuple[str, ...] = (),
    max_results: int = DEFAULT_MAX_RESULTS,
) -> list[Candidate]:
    """약관 검색과 본문 검증을 하나의 단계로 수행한다.

    기존처럼 먼저 '공식 홈페이지' 도메인을 추측하지 않는다. 이용약관 후보를 여러 방식으로
    찾고, 각 후보의 실제 본문을 검증한 뒤 통과한 문서의 최종 도메인만 공식 출처로 확정한다.
    """
    queries = (
        f'"{service_name}" 이용약관',
        f'"{service_name}" 공식 이용약관',
        f'"{service_name}" "terms of use"',
        f'"{service_name}" "terms of service"',
    )
    raw_candidates: dict[str, Candidate] = {}

    # 이미 검증한 서비스의 고정 약관 URL은 검색 결과보다 먼저 확인한다.
    for item in canonical_policy_candidates(service_name, trusted_domains):
        raw_candidates[item.url] = item

    search_succeeded = False
    for query in queries:
        try:
            results = client.search(
                query=query,
                search_depth="advanced",
                max_results=max(3, min(max_results, 8)),
                include_raw_content=False,
            ).get("results", [])
            search_succeeded = True
        except Exception:
            logging.exception("Terms verification search failed: %s", query)
            continue

        for rank, result in enumerate(results):
            url = normalize_url(result.get("url", ""))
            if not is_safe_terms_candidate_url(url):
                continue
            if trusted_domains and not is_official_url(url, trusted_domains):
                continue
            title = (result.get("title") or "").strip()
            snippet = (result.get("content") or "").strip()
            evidence = compact_text(f"{url} {title} {snippet}")
            if not any(compact_text(word) in evidence for word in DOCUMENT_KEYWORDS["terms"]):
                continue
            item = Candidate(
                url=url,
                title=title,
                snippet=snippet,
                requested_type="terms",
                detected_type="terms",
                score=max(0, 40 - rank * 4),
            )
            previous = raw_candidates.get(url)
            if previous is None or item.score > previous.score:
                raw_candidates[url] = item

    if not search_succeeded and not raw_candidates:
        logging.warning("All terms searches failed for %s", service_name)
        return []

    # 도메인별 최고 검증 문서만 남긴다. 같은 사이트의 중복·낮은 품질 페이지를 제거한다.
    per_domain: dict[str, Candidate] = {}
    for candidate in raw_candidates.values():
        verified = verify_terms_candidate(service_name, candidate, trusted_domains, client)
        if not verified:
            continue
        domain = registrable_domain(urlparse(verified.validated_final_url).netloc)
        previous = per_domain.get(domain)
        if previous is None or verified.score > previous.score:
            per_domain[domain] = verified

    return sorted(per_domain.values(), key=lambda item: item.score, reverse=True)


def split_into_chunks(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """RAG 검색에 사용할 겹치는 텍스트 청크를 생성한다."""
    text = normalize_text(text)
    if not text:
        return []
    if overlap >= chunk_size:
        raise ValueError("chunk overlap은 chunk size보다 작아야 합니다.")

    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 2 <= chunk_size:
            current = f"{current}\n\n{paragraph}".strip()
            continue
        if current:
            chunks.append(current)
        tail = current[-overlap:] if current else ""
        current = f"{tail}\n\n{paragraph}".strip()
    if current:
        chunks.append(current)
    return chunks


def classify_issue(issue: str) -> str:
    """신청서의 질문 의도 분류 단계에 사용할 간단한 초기 분류기."""
    text = issue.lower()
    keyword_groups = {
        "refund": ("환불", "refund", "돌려", "환급"),
        "cancellation": ("해지", "취소", "탈퇴", "cancel", "terminate"),
        "billing_autorenewal": ("자동결제", "정기결제", "다음 달", "갱신", "renewal"),
        "privacy": ("개인정보", "privacy", "정보 삭제", "보관"),
        "terms_change": ("약관 변경", "변경된 약관", "terms change"),
        "duplicate_charge": ("중복 결제", "두 번 결제", "duplicate charge"),
    }
    scores = {
        category: sum(1 for keyword in keywords if keyword in text)
        for category, keywords in keyword_groups.items()
    }
    category, score = max(scores.items(), key=lambda item: item[1])
    return category if score else "general_policy"


def make_document(
    service_name: str,
    document_type: str,
    title: str,
    source_url: str,
    source_kind: str,
    official_domain: bool,
    revision_date: str | None,
    selection_score: int,
    text: str,
    chunk_size: int,
    overlap: int,
) -> CollectedDocument | None:
    """본문을 정규화·청킹해 저장 가능한 문서 객체로 만든다."""
    text = normalize_text(text)
    if len(text) < 200:
        logging.info("Skipping short document: %s", source_url)
        return None
    chunks = split_into_chunks(text, chunk_size, overlap)
    return CollectedDocument(
        service_name=service_name,
        document_type=document_type,
        title=title or document_type,
        source_url=source_url,
        source_kind=source_kind,
        official_domain=official_domain,
        revision_date=revision_date,
        selection_score=selection_score,
        collected_at=datetime.now(timezone.utc).isoformat(),
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        text=text,
        chunks=chunks,
    )


def save_terms(
    base_dir: Path,
    service_name: str,
    terms_document: CollectedDocument,
) -> Path:
    """검증된 공식 이용약관 원문 한 건만 terms.txt로 저장한다."""
    output_dir = base_dir / "RAG" / "terms" / safe_service_name(service_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "terms.txt"
    output_path.write_text(terms_document.text, encoding="utf-8")
    return output_path


def print_candidates(candidates: list[Candidate], limit: int = 20) -> None:
    """--list 모드에서 점수와 탈락/선정 근거를 보여준다."""
    for index, item in enumerate(candidates[:limit]):
        reasons = ", ".join(item.reasons) or "no-signal"
        print(f"[{index}] {item.score:>4} | {item.detected_type:<20} | {item.url}")
        print(f"      {item.title} | {reasons}")


def prompt_for_terms_url(reason: str | None = None) -> str | None:
    """어느 자동 단계에서든 실패하면 사용자가 이용약관 URL을 직접 제공할 수 있게 한다."""
    if reason:
        print(reason)
    answer = input("이용약관 페이지의 URL을 복사해서 입력하시겠습니까? (y/n): ").strip().lower()
    if answer not in {"y", "yes", "예", "네"}:
        return None
    url = input("이용약관 페이지의 URL을 복사해서 입력해주세요: ").strip()
    if not url.startswith(("https://", "http://")):
        print("http:// 또는 https://로 시작하는 URL을 입력해주세요.")
        return None
    return normalize_url(url)


def request_verified_manual_candidate(
    service_name: str,
    client: TavilyClient | None,
    reason: str,
) -> Candidate | None:
    """사용자 제공 URL도 추출·리디렉션·약관 본문 검증을 거쳐서만 저장 후보로 만든다."""
    for attempt in range(2):
        url = prompt_for_terms_url(reason if attempt == 0 else "입력한 URL에서 이용약관 본문을 확인하지 못했습니다.")
        if not url:
            return None
        domain = registrable_domain(urlparse(url).netloc)
        candidate = Candidate(
            url=url,
            title=f"{service_name} 사용자 제공 이용약관",
            snippet="",
            requested_type="terms",
            detected_type="terms",
            canonical_source=True,
            score=900,
        )
        verified = verify_terms_candidate(
            service_name,
            candidate,
            (domain,),
            client,
            user_provided=True,
        )
        if verified:
            print(f"사용자 제공 이용약관 URL을 확인합니다: {verified.validated_final_url}")
            return verified
        logging.warning("Manual terms URL verification failed: %s", url)
    return None


def make_terms_document_from_candidate(
    service_name: str,
    candidate: Candidate,
    args: argparse.Namespace,
) -> CollectedDocument | None:
    """검증 완료 후보를 저장용 이용약관 문서로 변환한다."""
    text = candidate.validated_text
    if not text:
        return None
    revision_date = extract_revision_date(text)
    is_manual = "사용자 제공" in candidate.title
    if not revision_date and (has_current_terms_marker(text) or is_manual):
        revision_date = (
            "사용자 제공 URL (페이지 개정일 미표시)"
            if is_manual
            else "공식 페이지의 현행 약관 표기 확인"
        )
    if not revision_date and not args.allow_undated:
        logging.info("Skipping undated verified terms page: %s", candidate.validated_final_url)
        return None
    return make_document(
        service_name,
        "terms",
        candidate.title or "이용약관",
        candidate.validated_final_url or candidate.url,
        candidate.validated_source_kind or "web_unknown",
        True,
        revision_date,
        candidate.score,
        text,
        args.chunk_size,
        args.chunk_overlap,
    )


def parse_args() -> argparse.Namespace:
    """CLI 인자를 정의한다."""
    parser = argparse.ArgumentParser(description="FinePrint 약관·정책 문서 수집기")
    parser.add_argument("--service", help="구독형 서비스명")
    parser.add_argument(
        "--official-domain",
        action="append",
        default=[],
        help="공식 홈페이지 루트 도메인(예: netflix.com). 서비스별로 반복 가능",
    )
    parser.add_argument("--document", action="append", default=[], help="직접 지정할 PDF/TXT/MD 경로(반복 가능)")
    parser.add_argument("--issue", help="문제 상황. 입력하면 의도 분류 결과를 함께 출력")
    parser.add_argument("--list", action="store_true", help="검색 후보만 출력하고 본문은 수집하지 않음")
    parser.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    parser.add_argument("--top-k", type=int, default=20, help="본문을 실제 수집할 후보 수")
    parser.add_argument(
        "--allow-undated",
        action="store_true",
        help="개정일이 표시되지 않은 공식 이용약관도 저장할 때만 사용",
    )
    return parser.parse_args()


def main() -> int:
    """약관 후보 검색 → 실제 본문 검증 → 이용약관 원문 저장의 전체 흐름."""
    args = parse_args()
    base_dir = Path(__file__).resolve().parent
    configure_logging(base_dir)

    service_name = (args.service or input("구독형 서비스명을 입력하세요: ")).strip()
    if not service_name:
        print("서비스명이 비어 있습니다.")
        return 1

    trusted_domains = resolve_official_domains(service_name, args.official_domain)
    if args.issue:
        print(f"문제 유형 분류: {classify_issue(args.issue)}")

    client = None
    try:
        client = load_tavily_client()
    except RuntimeError as error:
        print(f"Tavily 검색은 생략합니다: {error}")

    # 핵심 변경: 홈페이지를 먼저 추측하지 않는다. 실제 약관 원문을 검증한 후보만 남긴다.
    candidates: list[Candidate] = []
    if client:
        candidates = search_verified_terms_candidates(
            client,
            service_name,
            trusted_domains,
            args.max_results,
        )

    if not candidates:
        failure_reason = (
            "자동 검색을 사용할 수 없습니다."
            if client is None
            else "자동 탐색 결과에서 본문·도메인·서비스명 검증을 모두 통과한 이용약관을 찾지 못했습니다."
        )
        manual_candidate = request_verified_manual_candidate(service_name, client, failure_reason)
        if not manual_candidate:
            print("검증 가능한 이용약관 URL이 없어 저장하지 않습니다.")
            return 1
        candidates = [manual_candidate]

    confirmed_domains = tuple(
        dict.fromkeys(registrable_domain(urlparse(item.validated_final_url).netloc) for item in candidates)
    )
    print(f"확인된 공식 도메인: {', '.join(confirmed_domains)}")
    print(f"본문 검증을 통과한 이용약관 후보 {len(candidates)}건을 찾았습니다.")
    if args.list:
        print_candidates(candidates)
        return 0

    documents: list[CollectedDocument] = []
    seen_hashes: set[str] = set()

    for candidate in candidates[: max(args.top_k, 0)]:
        document = make_terms_document_from_candidate(service_name, candidate, args)
        if document and document.sha256 not in seen_hashes:
            documents.append(document)
            seen_hashes.add(document.sha256)

    # 웹 탐색이 실패했거나 특정 약관을 직접 지정한 경우 PDF/TXT를 함께 인입한다.
    for document_path in args.document:
        try:
            text, source_kind = extract_local_document(document_path)
            local_type = classify_document_type(document_path, Path(document_path).stem, text[:2000], "terms")
            document = make_document(
                service_name,
                local_type,
                Path(document_path).name,
                str(Path(document_path).resolve()),
                source_kind,
                False,
                extract_revision_date(text),
                0,
                text,
                args.chunk_size,
                args.chunk_overlap,
            )
            if document and document.sha256 not in seen_hashes:
                documents.append(document)
                seen_hashes.add(document.sha256)
        except Exception as error:
            logging.exception("Local document ingestion failed: %s", document_path)
            print(f"직접 문서 처리 실패: {document_path} ({error})")

    if not documents:
        manual_candidate = request_verified_manual_candidate(
            service_name,
            client,
            "자동 후보의 개정일 또는 본문 검증에 실패했습니다.",
        )
        if manual_candidate:
            document = make_terms_document_from_candidate(service_name, manual_candidate, args)
            if document:
                documents.append(document)
        if not documents:
            print("본문을 확보한 이용약관이 없습니다. --document로 PDF/TXT를 직접 지정해 보세요.")
            print_candidates(candidates, limit=10)
            return 1

    official_terms = [
        document for document in documents
        if document.document_type == "terms"
        and document.official_domain
        and document.revision_date
    ]
    if not official_terms:
        manual_candidate = request_verified_manual_candidate(
            service_name,
            client,
            "개정일이 확인된 공식 이용약관을 찾지 못했습니다.",
        )
        if manual_candidate:
            manual_document = make_terms_document_from_candidate(service_name, manual_candidate, args)
            if manual_document:
                official_terms = [manual_document]
        if not official_terms:
            print("개정일이 확인된 공식 이용약관 원문을 찾지 못해 저장하지 않습니다.")
            return 1

    primary_terms = max(official_terms, key=lambda document: document.selection_score)
    output_path = save_terms(base_dir, service_name, primary_terms)
    print("수집 완료: 공식 이용약관 1개 문서")
    print(f"저장 위치: {output_path}")
    print(f"공식 이용약관: {primary_terms.source_url}")
    print(f"문서 개정일: {primary_terms.revision_date}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
