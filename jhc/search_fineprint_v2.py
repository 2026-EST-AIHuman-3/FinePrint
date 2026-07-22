"""구독형 서비스의 공식 약관과 개인정보처리방침을 수집한다.

1. FinePrint 프로젝트 루트로 이동
cd /smhrd2/FinePrint

2. Conda 환경 활성화
conda activate fineprint311

3. 실행
python -m jhc.search_fineprint_v2

설치:
    pip install tavily-python playwright trafilatura requests python-dotenv
    python -m playwright install chromium

API 키 입력:
    unset TAVILY_API_KEY
    export TAVILY_API_KEY="키 입력"

실행:
    # .env 파일 또는 환경 변수에 TAVILY_API_KEY를 설정한 뒤 실행
    python -m jhc.search_fineprint_v2
    python -m jhc.search_fineprint_v2 --service 넷플릭스
    python -m jhc.search_fineprint_v2 --service 넷플릭스 --official-domain netflix.com
    python -m jhc.search_fineprint_v2 --service 넷플릭스 \
        --terms-url https://help.netflix.com/ko/legal/termsofuse \
        --privacy-url https://help.netflix.com/ko/legal/privacy

저장 파일:
    <FinePrint 데이터 경로>/terms/<서비스명>/terms.txt
    <FinePrint 데이터 경로>/terms/<서비스명>/privacy.txt

각 파일은 첫 줄에 실제로 수집한 최종 참조 URL을 기록하고, 그 아래에는
페이지에서 추출한 본문을 별도의 정규화·요약·번역 없이 저장한다.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_ROOT = Path(
    os.getenv(
        "FINEPRINT_POLICY_DATA_PATH",
        str(Path(__file__).resolve().parent / "RAG"),
    )
).expanduser().resolve()


DOCUMENTS = {
    "terms": {
        "label": "약관",
        "filename": "terms.txt",
        "queries": (
            "{service} 이용약관",
            "{service} terms of service",
        ),
        "keywords": (
            "이용약관", "서비스 이용약관", "terms of service", "terms of use",
            "terms and conditions",
        ),
    },
    "privacy": {
        "label": "개인정보처리방침",
        "filename": "privacy.txt",
        "queries": (
            "{service} 개인정보처리방침",
            "{service} privacy policy",
        ),
        "keywords": (
            "개인정보처리방침", "개인정보 보호정책", "개인정보", "privacy policy",
            "privacy statement", "personal information policy",
        ),
    },
}

USER_AGENT = "Mozilla/5.0 (Policy collector; contact: policy-collector@example.invalid)"
MINIMUM_EXTRACTED_BODY_LENGTH = 200
POLICY_CONTAINER_SELECTOR = (
    "#printDiv, .policy-content, .terms-content, .privacy-content, .topic-main"
)
IGNORED_HOSTS = (
    "google.", "bing.com", "naver.com", "daum.net", "wikipedia.org", "reddit.com",
    "youtube.com", "facebook.com", "instagram.com", "x.com", "twitter.com",
    "tistory.com", "medium.com", "brunch.co.kr", "blog.naver.com",
)

# Tavily 검색 이전에 확인할 수 있는 공식 정책 페이지다. aliases를 추가하면
# 서비스명 표기가 한글/영문으로 달라도 같은 공식 도메인과 URL을 사용한다.
SERVICE_PROFILES = (
    {
        "aliases": ("netflix", "넷플릭스"),
        "official_domain": "netflix.com",
        "policy_urls": {
            "terms": ("https://help.netflix.com/ko/legal/termsofuse",),
            "privacy": ("https://help.netflix.com/ko/legal/privacy",),
        },
    },
    {
        "aliases": ("tving", "티빙"),
        "official_domain": "tving.com",
        "policy_urls": {
            "terms": ("https://www.tving.com/policy/terms",),
            "privacy": ("https://www.tving.com/policy/privacy",),
        },
    },
    {
        "aliases": (
            "disneyplus", "disney plus", "disney+", "디즈니플러스", "디즈니 플러스", "디즈니+",
        ),
        "official_domain": "disneyplus.com",
        "policy_urls": {
            # 법률센터의 메뉴 URL이 아니라 실제 본문을 게시하는 공식 페이지다.
            "terms": ("https://www.disneyplus.com/ko-kr/welcome/subscriber-agreement",),
            # 한국 이용자 대상 개인정보 처리방침 부속서다.
            "privacy": ("https://www.disneyplus.com/ko-kr/welcome/supplemental-privacy-policy",),
        },
    },
)


@dataclass(frozen=True)
class ExtractedPage:
    """추출 결과. text는 추출기가 돌려준 문자열을 그대로 보관한다."""

    text: str
    final_url: str
    method: str
    title: str = ""


def load_tavily_client():
    """환경 변수에서 Tavily 클라이언트를 만든다. 없으면 None을 반환한다."""
    try:
        from dotenv import load_dotenv
        from tavily import TavilyClient
    except ImportError:
        return None

    # 실행 위치와 관계없이 이 파일 옆의 .env도 읽는다.
    load_dotenv(Path(__file__).resolve().parent / ".env")
    api_key = os.getenv("TAVILY_API_KEY")
    return TavilyClient(api_key=api_key) if api_key else None


def compact_service_name(service_name: str) -> str:
    """서비스 별칭 비교에 쓸 공백·기호 없는 이름을 반환한다."""
    return re.sub(r"[^0-9a-z가-힣]", "", service_name.lower())


def find_service_profile(service_name: str) -> dict | None:
    """입력 서비스명과 일치하는 공식 도메인/정책 URL 프로필을 찾는다."""
    service_key = compact_service_name(service_name)
    for profile in SERVICE_PROFILES:
        if service_key in {compact_service_name(alias) for alias in profile["aliases"]}:
            return profile
    return None


def normalized_host(value: str) -> str:
    """URL 또는 도메인 입력값에서 비교용 호스트 이름을 얻는다."""
    candidate = value.strip().lower()
    if not candidate:
        return ""
    if "://" not in candidate:
        candidate = "https://" + candidate
    return (urlparse(candidate).hostname or "").lower()


def is_in_domain(url: str, official_domain: str) -> bool:
    """리디렉션 후 주소까지 공식 도메인 또는 그 하위 도메인인지 검사한다."""
    host = normalized_host(url)
    domain = normalized_host(official_domain)
    return bool(host and domain and (host == domain or host.endswith("." + domain)))


def is_usable_url(url: str) -> bool:
    host = normalized_host(url)
    return url.startswith(("https://", "http://")) and not any(
        bad in host for bad in IGNORED_HOSTS
    )


def result_items(response: object) -> Iterable[dict]:
    """Tavily 응답의 결과 목록을 안전하게 꺼낸다."""
    if isinstance(response, dict):
        results = response.get("results", [])
        if isinstance(results, list):
            return (item for item in results if isinstance(item, dict))
    return ()


def discover_official_domain(client, service_name: str) -> str | None:
    """Tavily의 공식 홈페이지 검색 결과에서 서비스명과 일치하는 도메인을 고른다.

    자동 판별은 보수적으로 한다. 신뢰할 만한 도메인을 찾지 못하면 빈 값을
    반환해, 이후 사용자가 공식 URL을 직접 제공하도록 한다.
    """
    service_key = compact_service_name(service_name)
    best: tuple[int, str] | None = None

    for query in (f'"{service_name}" 공식 홈페이지', f'"{service_name}" official site'):
        try:
            response = client.search(
                query=query,
                search_depth="advanced",
                max_results=8,
                include_raw_content=False,
            )
        except Exception as error:  # 네트워크/쿼터 오류는 수동 입력으로 처리한다.
            print(f"공식 홈페이지 검색 실패: {error}")
            continue

        for rank, item in enumerate(result_items(response)):
            url = str(item.get("url", ""))
            if not is_usable_url(url):
                continue
            host = normalized_host(url)
            title_and_snippet = f"{item.get('title', '')} {item.get('content', '')}".lower()
            compact_host = re.sub(r"[^0-9a-z가-힣]", "", host)
            score = 20 - rank
            if service_key and service_key in compact_host:
                score += 80
            if "official" in title_and_snippet or "공식" in title_and_snippet:
                score += 25
            if urlparse(url).path in ("", "/"):
                score += 10
            if best is None or score > best[0]:
                best = (score, host)

    # 서비스명과 도메인 일치 또는 공식 표기 등, 충분한 근거가 있을 때만 사용한다.
    return best[1] if best and best[0] >= 60 else None


def search_policy_urls(client, service_name: str, document_type: str, official_domain: str) -> list[str]:
    """공식 도메인으로 제한한 Tavily 검색 결과만 반환한다.

    문서당 한 번의 넓은 검색으로 최대 10개 후보를 얻는다. 기존의 여러 개
    따옴표 검색보다 Tavily 사용량과 API 한도 소모를 줄이면서도 결과 수를 늘린다.
    """
    seen: set[str] = set()
    urls: list[str] = []
    query = DOCUMENTS[document_type]["queries"][0].format(service=service_name)
    try:
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=10,
            include_domains=[official_domain],
            include_raw_content=False,
        )
    except Exception as error:
        print(f"{DOCUMENTS[document_type]['label']} 검색 실패: {error}")
        return urls
    for item in result_items(response):
        url = str(item.get("url", ""))
        if is_in_domain(url, official_domain) and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def extract_with_playwright(url: str) -> ExtractedPage | None:
    """자바스크립트 페이지를 렌더링해 정책 본문을 추출한다.

    광고·분석 연결을 계속 유지하는 사이트는 ``networkidle`` 상태에 도달하지 않을
    수 있다. 따라서 DOM이 준비된 시점부터 정책 본문 영역이 채워질 때까지 기다린다.
    TVING처럼 ``#printDiv`` 안에 본문을 동적으로 넣는 페이지도 이 방식으로 처리한다.
    반환된 inner_text에는 공백 정리나 문장 재작성 처리를 하지 않는다.
    """
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=USER_AGENT)
                # networkidle은 광고/분석 소켓 때문에 끝나지 않는 경우가 있어 사용하지 않는다.
                page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                title = page.title()

                # 정책 전용 컨테이너가 있는 동적 페이지에서만 본문 주입을 기다린다.
                # 없는 정적 페이지까지 20초씩 기다리지 않아 수집 시간이 크게 줄어든다.
                if page.locator(POLICY_CONTAINER_SELECTOR).count() > 0:
                    try:
                        page.wait_for_function(
                            """() => {
                                const target = document.querySelector(
                                    '#printDiv, .policy-content, .terms-content, .privacy-content, .topic-main'
                                );
                                return Boolean(target && (target.innerText || '').trim().length >= 200);
                            }""",
                            timeout=20_000,
                            polling=500,
                        )
                    except PlaywrightTimeoutError:
                        # 렌더링은 완료됐지만 전용 선택자가 없는 경우 아래의 일반 추출도 시도한다.
                        page.wait_for_timeout(1_000)
                else:
                    page.wait_for_timeout(1_000)

                text = extract_text_from_rendered_page(page)
                if len(text.strip()) < MINIMUM_EXTRACTED_BODY_LENGTH:
                    print(f"렌더링된 본문이 너무 짧아 저장하지 않습니다 ({url}).")
                    return None
                return ExtractedPage(
                    text=text, final_url=page.url, method="playwright", title=title
                )
            finally:
                browser.close()
    except Exception as error:
        print(f"Playwright 본문 추출 실패 ({url}): {error}")
        return None


def extract_text_from_rendered_page(page) -> str:
    """정책 전용 영역을 우선해 브라우저에 렌더링된 텍스트를 그대로 읽는다."""
    selectors = (
        "#printDiv",  # TVING 등 인쇄용 정책 본문 컨테이너
        ".policy-content",
        ".terms-content",
        ".privacy-content",
        ".topic-main",
        "main article",
        "article",
        "[role='main']",
        "main",
        "body",
    )
    # 본문을 iframe에 담는 사이트도 있으므로 최상위 프레임과 하위 프레임을 확인한다.
    for frame in page.frames:
        for selector in selectors:
            locator = frame.locator(selector).first
            try:
                if locator.count() == 0:
                    continue
                text = locator.inner_text(timeout=5_000)
            except Exception:
                continue
            if len(text.strip()) >= MINIMUM_EXTRACTED_BODY_LENGTH:
                return text
    return ""


def extract_with_trafilatura(url: str) -> ExtractedPage | None:
    """정적 페이지 또는 Playwright 실패 시 trafilatura로 본문을 추출한다."""
    try:
        import requests
        import trafilatura
    except ImportError:
        return None

    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        response.raise_for_status()
        text = trafilatura.extract(
            response.text,
            output_format="txt",
            include_comments=False,
            include_tables=True,
            include_links=False,
            deduplicate=False,
        )
        if not text or len(text.strip()) < MINIMUM_EXTRACTED_BODY_LENGTH:
            return None
        return ExtractedPage(
            text=text,
            final_url=response.url,
            method="trafilatura",
            title="",
        )
    except Exception as error:
        print(f"trafilatura 본문 추출 실패 ({url}): {error}")
        return None


def extract_page(url: str) -> ExtractedPage | None:
    """렌더링 추출을 먼저 시도하고 정적 본문 추출을 보조 수단으로 사용한다."""
    page = extract_with_playwright(url)
    if page and page.text.strip():
        return page
    return extract_with_trafilatura(url)


def looks_like_requested_policy(page: ExtractedPage, document_type: str) -> bool:
    """검색 결과가 다른 문서가 아닌지 제목·URL·초반 본문으로 최소 검증한다."""
    # 검증에만 lower/strip을 사용하며 저장할 page.text는 절대 변경하지 않는다.
    evidence = f"{page.final_url}\n{page.title}\n{page.text[:8000]}".lower()
    keywords = DOCUMENTS[document_type]["keywords"]
    return any(keyword.lower() in evidence for keyword in keywords) and len(page.text.strip()) >= 200


def ask_yes_no(question: str) -> bool:
    while True:
        answer = input(f"{question} (y/n): ").strip().lower()
        if answer in {"y", "yes", "네", "예"}:
            return True
        if answer in {"n", "no", "아니오"}:
            return False
        print("y 또는 n으로 입력해 주세요.")


def ask_manual_url(service_name: str, document_type: str, official_domain: str | None) -> ExtractedPage | None:
    """자동 검색 실패 시 사용자 URL의 본문을 그대로 수집한다.

    수동 URL은 사용자가 공식 페이지임을 확인해 제공한 것으로 간주한다. 따라서
    자동 검색에서 사용하던 도메인·문서 유형·키워드 검증을 다시 적용하지 않는다.
    페이지에서 텍스트를 하나도 추출할 수 없는 경우에만 재입력을 요청한다.
    """
    label = DOCUMENTS[document_type]["label"]
    if not ask_yes_no(f"{label}을 찾지 못했습니다. 공식 페이지 URL을 직접 입력하시겠습니까?"):
        return None

    for _ in range(2):
        url = input(f"{service_name}의 공식 {label} URL: ").strip()
        if not url.startswith(("https://", "http://")):
            print("http:// 또는 https://로 시작하는 URL을 입력해 주세요.")
            continue

        page = extract_page(url)
        # 수동 입력 페이지는 약관/방침 키워드 여부와 관계없이 추출 본문을 저장한다.
        if page and page.text.strip():
            return page
        print("입력한 URL에서 본문을 추출하지 못했습니다. URL을 확인한 뒤 다시 입력해 주세요.")
    return None


def policy_from_user_url(url: str, document_type: str) -> ExtractedPage | None:
    """UI/CLI에서 명시적으로 받은 공식 URL의 본문을 추출한다.

    사용자가 문서 종류를 직접 지정했으므로 자동 검색용 키워드 판정은 적용하지
    않는다. URL 형식과 실제 본문 추출 가능 여부만 확인한다.
    """
    candidate = url.strip()
    if not candidate.startswith(("https://", "http://")):
        print(f"{DOCUMENTS[document_type]['label']} URL 형식이 올바르지 않습니다: {url}")
        return None
    page = extract_page(candidate)
    if page and page.text.strip():
        return page
    print(f"입력 URL에서 본문을 추출하지 못했습니다: {candidate}")
    return None


def policy_from_search(client, service_name: str, document_type: str, official_domain: str) -> ExtractedPage | None:
    """검색 URL을 하나씩 열고, 최종 리디렉션 URL까지 공식 도메인인지 검증한다."""
    for url in search_policy_urls(client, service_name, document_type, official_domain):
        page = extract_page(url)
        if not page:
            continue
        if not is_in_domain(page.final_url, official_domain):
            print(f"공식 도메인 밖으로 리디렉션되어 제외: {page.final_url}")
            continue
        if looks_like_requested_policy(page, document_type):
            return page
    return None


def policy_from_known_urls(
    profile: dict | None, document_type: str, official_domain: str
) -> ExtractedPage | None:
    """등록된 공식 정책 URL을 Tavily보다 먼저 확인한다.

    정책 URL이 안정적으로 알려진 서비스는 검색 API의 쿼터·순위·색인 상태와
    무관하게 수집할 수 있다. 페이지 본문과 최종 리디렉션 도메인은 동일하게 검증한다.
    """
    if not profile:
        return None
    for url in profile["policy_urls"].get(document_type, ()):
        page = extract_page(url)
        if not page:
            continue
        if not is_in_domain(page.final_url, official_domain):
            print(f"등록된 URL이 공식 도메인 밖으로 리디렉션되어 제외: {page.final_url}")
            continue
        if looks_like_requested_policy(page, document_type):
            return page
    return None


def safe_service_directory_name(service_name: str) -> str:
    """입력 이름을 최대한 유지하되 Windows에서 금지한 파일명 문자만 바꾼다."""
    name = unicodedata.normalize("NFKC", service_name).strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).rstrip(". ")
    return name or "unnamed_service"


def save_policy(data_root: Path, service_name: str, document_type: str, page: ExtractedPage) -> Path:
    """참조 URL과 원문을 UTF-8 텍스트 파일로 원자적으로 저장한다."""
    output_dir = data_root / "terms" / safe_service_directory_name(service_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / DOCUMENTS[document_type]["filename"]

    # 본문은 추출 결과를 그대로 쓰며, URL 표기용 메타데이터만 앞에 추가한다.
    content = f"참조 URL: {page.final_url}\n\n{page.text}"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", delete=False, dir=output_dir, suffix=".tmp"
    ) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    temporary_path.replace(output_path)
    return output_path


def collect_service_policies(
    service_name: str,
    official_domain: str | None = None,
    output_root: str | Path | None = None,
    document_types: Iterable[str] = ("terms", "privacy"),
    policy_urls: dict[str, str] | None = None,
    allow_manual_url: bool = False,
) -> list[Path]:
    """서비스의 공식 정책을 수집하고 인제스트 대상 파일 경로를 반환한다.

    Agent에서는 ``allow_manual_url=False``로 호출해 입력 대기 없이 실패를
    반환하고, CLI에서는 True로 호출해 자동 탐색 실패 시 공식 URL을 받을 수 있다.
    """
    service_name = service_name.strip()
    if not service_name:
        raise ValueError("service_name은 빈 값일 수 없습니다.")

    requested_types = tuple(dict.fromkeys(document_types))
    invalid_types = [name for name in requested_types if name not in DOCUMENTS]
    if invalid_types:
        raise ValueError(f"지원하지 않는 문서 유형입니다: {invalid_types}")

    explicit_urls = {
        document_type: url.strip()
        for document_type, url in (policy_urls or {}).items()
        if url and url.strip()
    }
    invalid_url_types = [name for name in explicit_urls if name not in DOCUMENTS]
    if invalid_url_types:
        raise ValueError(f"지원하지 않는 URL 문서 유형입니다: {invalid_url_types}")

    data_root = Path(output_root).expanduser().resolve() if output_root else DEFAULT_DATA_ROOT
    client = load_tavily_client()
    profile = find_service_profile(service_name)
    resolved_domain = normalized_host(official_domain or "") or (
        profile["official_domain"] if profile else None
    )
    if not resolved_domain and explicit_urls:
        resolved_domain = normalized_host(next(iter(explicit_urls.values()))) or None

    if profile and not official_domain:
        print("등록된 공식 정책 URL 후보를 먼저 확인합니다.")
    if not resolved_domain and client:
        resolved_domain = discover_official_domain(client, service_name)

    if resolved_domain:
        print(f"검색에 사용할 공식 도메인: {resolved_domain}")
    else:
        print("공식 도메인을 자동 확인하지 못했습니다.")

    saved: list[Path] = []
    for document_type in requested_types:
        explicit_url = explicit_urls.get(document_type)
        page = (
            policy_from_user_url(explicit_url, document_type)
            if explicit_url
            else None
        )
        if page is None and not explicit_url:
            page = (
                policy_from_known_urls(profile, document_type, resolved_domain)
                if resolved_domain
                else None
            )
        if page is None and client and resolved_domain:
            page = policy_from_search(
                client,
                service_name,
                document_type,
                resolved_domain,
            )
        if page is None and allow_manual_url:
            page = ask_manual_url(service_name, document_type, resolved_domain)
        if page is None:
            print(f"{DOCUMENTS[document_type]['label']}은 저장하지 않았습니다.")
            continue

        output_path = save_policy(data_root, service_name, document_type, page)
        saved.append(output_path)
        print(f"{DOCUMENTS[document_type]['label']} 저장 완료: {output_path}")
        print(f"참조 URL: {page.final_url}")

    return saved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="공식 약관 및 개인정보처리방침 수집기")
    parser.add_argument("--service", help="구독형 서비스명 (생략 시 실행 중 입력)")
    parser.add_argument(
        "--official-domain",
        help="공식 도메인. 예: netflix.com. 지정하면 이 도메인과 하위 도메인만 검색합니다.",
    )
    parser.add_argument("--terms-url", help="사용자가 직접 지정한 공식 이용약관 URL")
    parser.add_argument("--privacy-url", help="사용자가 직접 지정한 공식 개인정보처리방침 URL")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_DATA_ROOT,
        help="수집 문서를 저장할 공용 데이터 폴더",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="자동 탐색 실패 시 URL 입력을 요청하지 않습니다.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    service_name = (args.service or input("구독형 서비스명을 입력하세요: ")).strip()
    if not service_name:
        print("서비스명이 비어 있어 종료합니다.")
        return 1

    saved = collect_service_policies(
        service_name=service_name,
        official_domain=args.official_domain,
        output_root=args.output_root,
        policy_urls={
            "terms": args.terms_url,
            "privacy": args.privacy_url,
        },
        allow_manual_url=not args.non_interactive,
    )

    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())
