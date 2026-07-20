"""
1. 프로젝트 폴더로 이동
cd /smhrd2/FinePrint/jhc

2. Conda 환경 활성화
conda activate fineprint311

3. 필요한 라이브러리 설치 (최초 1회만)
pip install tavily-python requests PyPDF2 playwright openai python-dotenv

4. Playwright 브라우저 설치 (최초 1회만)
playwright install

5. 환경 변수 등록
export TAVILY_API_KEY="TAVILY_API_KEY"
export OPENAI_API_KEY="OPENAI_API_KEY"

6. 프로그램 실행
python search_tos_v2.py
"""

import os
import json
from tavily import TavilyClient
from openai import OpenAI
from urllib.parse import urlparse
import tempfile
import requests
from PyPDF2 import PdfReader
from playwright.sync_api import sync_playwright
import logging
import time
import re
import unicodedata
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # python-dotenv 미설치: 환경변수를 직접 설정한 경우엔 문제없음
    logging.info('python-dotenv not available; skipping .env load')

# 1. API 키 등록
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def ensure_api_keys():
    if not TAVILY_API_KEY:
        print('필수 환경변수 TAVILY_API_KEY가 설정되어 있지 않습니다.')
        print('예: export TAVILY_API_KEY="your_tavily_api_key_here"')
        raise SystemExit(1)

tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
openai_client = None
if OPENAI_API_KEY:
    try:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        openai_client = None
else:
    print('환경변수 OPENAI_API_KEY가 설정되어 있지 않습니다. OpenAI 기반 폴백은 사용되지 않습니다.')

def ensure_playwright_installed():
    try:
        from playwright.sync_api import sync_playwright as _sp
    except Exception:
        print('Playwright가 설치되어 있지 않거나 불완전합니다.')
        print('설치 예시:')
        print('pip install playwright')
        print('python -m playwright install')
        raise SystemExit(1)
    # 간단한 런치 테스트
    try:
        with _sp() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
    except Exception:
        print('Playwright 브라우저 바이너리가 설치되지 않았거나 실행할 수 없습니다.')
        print('브라우저 설치 명령을 실행하세요:')
        print('python -m playwright install')
        raise SystemExit(1)

# 로깅 설정
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, 'extract.log'),
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)

# 블랙리스트 도메인/호스트 패턴 (간단한 휴리스틱)
SITE_TYPE_BLACKLIST = [
    "blog", "medium.com", "wordpress.com", "tistory.com", "brunch.co.kr",
    "koreaherald", "kr-", "wikipedia.org", "reddit.com",
    "koreajoongangdaily.com", "joongang.co.kr", "naver.com/news", "hankyung.com", "chosun.com", "hani.co.kr"
]

# 도메인 또는 호스트에 특정 키워드가 포함되어 있으면 집계/요약 사이트로 간주하여 제외
AGGREGATOR_HOST_KEYWORDS = [
    "terms", "tos-watchdog", "tos", "terms-of-service", "toswatchdog", "terms.law"
]

# 약관 전형적 경로 키워드
TERMS_PATH_KEYWORDS = [
    "terms", "terms-of-service", "terms_and_conditions", "tos", "legal", "policy", "privacy"
]

# 명시적으로 제외할 플랫폼/호스트 (스토어 및 블로그)
PLATFORM_DOMAINS = ["apps.apple.com", "play.google.com", "blog.naver.com", "aptoide.com"]

# OpenAI prompt templates
SYSTEM_PROMPT_TEMPLATE = """
너는 구독형 서비스의 '이용약관 원문 페이지'만을 정확히 골라내는 판별기다.
아래 검색 결과 목록을 검토하여, 진짜 이용약관 원문일 가능성이 높은 순서대로 정렬하라.
[출력 규칙]
반드시 아래 JSON 형식으로만 답하라.
{"ranked_indices": [<가능성이 높은 순서대로 나열한 번호들>]}
"""

USER_PROMPT_TEMPLATE = (
    "서비스명: {service_name}\n\n"
    "검색 결과 목록(각 항목: 인덱스, URL, 제목, 내용 요약):\n{listing}\n\n"
    "위 목록을 검토해 '이용약관 원문'일 가능성이 높은 순서대로 인덱스를 JSON 배열로 반환하세요. "
    "출력 형식: {{\"ranked_indices\": [index,...]}}"
)

def get_service_name():
    return input("구독형 서비스명을 입력하세요: ").strip()

def search_tos(service_name, max_results=10):
    # 서비스명이 로마자로 적혀 있어도(예: tving, wavve, coupang) 실제로는 한국 서비스인 경우가 많고,
    # 그 경우 약관 페이지는 한국어("이용약관")로 되어 있어 영문 "terms" 쿼리만으로는 잘 안 잡힙니다.
    # 따라서 서비스명의 표기 문자와 무관하게 한글/영문 쿼리를 항상 함께 시도합니다.
    query = f"{service_name} 약관 OR {service_name} terms"
    response = tavily_client.search(
        query=query,
        search_depth="advanced",
        max_results=max_results,
        include_raw_content=False,
    )
    results = response.get("results", [])
    # 검색 단계에서 앱스토어/플레이스토어/블로그 결과 제거
    filtered = []
    for r in results:
        url = (r.get('url') or '').lower()
        host = urlparse(url).netloc.lower() if url else ''
        if any(p in host for p in PLATFORM_DOMAINS) or any(p in url for p in PLATFORM_DOMAINS):
            logging.info(f"Filtering out platform/blog search result: {url}")
            continue
        filtered.append(r)
    # If no good candidates found, try a stricter query focusing on inurl/intitle patterns
    if not filtered:
        stricter_parts = [f"{service_name} inurl:terms", f"{service_name} inurl:policy", f"{service_name} intitle:약관", f"{service_name} intitle:이용약관"]
        stricter_query = " OR ".join(stricter_parts)
        logging.info(f"No candidates after initial filter; trying stricter query: {stricter_query}")
        try:
            resp2 = tavily_client.search(
                query=stricter_query,
                search_depth="advanced",
                max_results=max_results,
                include_raw_content=False,
            )
            results2 = resp2.get("results", [])
            for r in results2:
                url = (r.get('url') or '').lower()
                host = urlparse(url).netloc.lower() if url else ''
                if any(p in host for p in PLATFORM_DOMAINS) or any(p in url for p in PLATFORM_DOMAINS):
                    continue
                filtered.append(r)
        except Exception:
            logging.exception("Stricter query failed")

    # If still empty or no path/content evidence, try expanded variant list (legacy behavior)
    evidence_found = any(url_path_has_terms(r.get('url','')) or content_looks_like_terms(r.get('content','')) for r in filtered)
    if not filtered or not evidence_found:
        # expanded variants
        korean_variants = ["약관", "이용약관", "이용 약관", "이용약관 안내"]
        english_variants = ["terms", "terms of service", "terms-of-service", "privacy policy"]
        q_parts = [f"{service_name} {v}" for v in (korean_variants + english_variants)]
        expanded_query = " OR ".join(q_parts)
        logging.info(f"Trying expanded variants query: {expanded_query}")
        try:
            resp3 = tavily_client.search(
                query=expanded_query,
                search_depth="advanced",
                max_results=max_results,
                include_raw_content=False,
            )
            res3 = resp3.get('results', [])
            for r in res3:
                url = (r.get('url') or '').lower()
                host = urlparse(url).netloc.lower() if url else ''
                if any(p in host for p in PLATFORM_DOMAINS) or any(p in url for p in PLATFORM_DOMAINS):
                    continue
                filtered.append(r)
        except Exception:
            logging.exception('Expanded variants query failed')

    return filtered


def is_official_domain(url, service_name):
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    # 서비스명이 도메인에 포함되거나 전형적 공식 도메인 형태인 경우 우대
    if service_name.lower().replace(' ', '') in host:
        return True
    # common official endings (회사 도메인 추정)
    for suf in [".com", ".co", ".kr", ".io", ".net"]:
        if host.endswith(suf) and service_name.split()[0].lower() in host:
            return True
    return False

def host_related(url, service_name):
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    name = service_name.lower().replace(' ', '')
    # 서비스명 토큰이 도메인에 포함되면 관련 있음
    if name and name in host:
        return True
    # 일부 일반적 변형 허용 (예: fcdaum -> fnbpeople, check keywords)
    tokens = [t for t in re.split(r'[^0-9a-zA-Z가-힣]+', service_name.lower()) if t]
    for t in tokens:
        if t and t in host:
            return True
    return False

def url_path_has_terms(url):
    parsed = urlparse(url)
    # path뿐 아니라 query string도 함께 검사합니다.
    # 예: https://www.youtube.com/static?template=terms&hl=ko&gl=KR 처럼
    # 실제 페이지 종류가 path가 아닌 query parameter로 지정되는 경우가 있습니다.
    path_and_query = f"{parsed.path}?{parsed.query}".lower()
    return any(k in path_and_query for k in TERMS_PATH_KEYWORDS)

def content_looks_like_terms(content):
    if not content:
        return False
    c = content[:8000]
    # 더 엄격한 판단: 조항 표기가 여러 번 나타나거나 'Article'이 여러 번 등장해야 인정
    kor_clause_count = c.count('제') + c.count('조')
    eng_article_count = c.lower().count('article')
    terms_phrase = 'terms and conditions' in c.lower() or 'terms of service' in c.lower()
    # 숫자/조합 패턴 예: '제1조', '제2조', '제 1조' 등
    numbered_clause = any(f"제{i}조" in c for i in range(1, 21))
    # 기준: 한국어 조항이 적어도 2회 이상 또는 영어 Article 2회 이상, 혹은 명시적 terms phrase
    if numbered_clause or kor_clause_count >= 2 or eng_article_count >= 2 or terms_phrase:
        return True
    return False

def is_news_article(content, url):
    if not content:
        return False
    c = content[:2000].lower()
    news_indicators = ['기사', '입력', '출처', '기자', '연합뉴스', '중앙일보', '조선일보', '헤럴드', 'press', 'news']
    # URL 패턴으로도 뉴스 포맷 판별 (예: daum.v / v/ 등)
    u = urlparse(url)
    if '/v/' in u.path or '/news/' in u.path:
        return True
    score = sum(1 for kw in news_indicators if kw in c)
    # 여러 뉴스 지표가 발견되면 뉴스로 판단
    # 추가: '기자' 패턴(예: '홍길동 기자') 출현 횟수 세기
    reporter_mentions = len(re.findall(r"[\w가-힣]{1,20}\s*기자", content)) + len(re.findall(r"기자[\s,，。.]", content))
    # 기사 키워드 2개 이상 또는 기자 언급이 1회 이상이면 뉴스로 판단
    return score >= 2 or reporter_mentions >= 1

def count_reporter_mentions(content):
    if not content:
        return 0
    return len(re.findall(r"[\w가-힣]{1,20}\s*기자", content)) + len(re.findall(r"기자[\s,，。.]", content))

def domain_is_blacklisted(url):
    host = urlparse(url).netloc.lower()
    if any(b in host for b in SITE_TYPE_BLACKLIST):
        return True
    # 집계/요약 도메인 키워드 배제
    if any(k in host for k in AGGREGATOR_HOST_KEYWORDS):
        return True
    return False


# ---------------------------------------------------------------------------
# 점수 체계 (SCORE_WEIGHTS)
# 각 항목이 왜/얼마나 점수에 영향을 주는지 한 곳에서 관리합니다.
# 값을 조정하고 싶으면 이 딕셔너리만 수정하면 됩니다.
# ---------------------------------------------------------------------------
SCORE_WEIGHTS = {
    "path_or_query_terms": 100,   # URL 경로/쿼리스트링에 terms/약관 관련 키워드가 있을 때
    "content_terms": 60,          # 본문(스니펫)이 실제 약관처럼 보일 때 (제N조, Article 등)
    "root_path_penalty": -40,     # 루트 경로('/')만 가리키는 URL (약관 페이지일 가능성 낮음)
    "blacklisted_domain": -40,    # 블랙리스트 도메인 (블로그, 뉴스, 집계 사이트 등)
    "official_domain_bonus": 80,  # 공식 도메인이면서 경로/본문 증거가 있을 때 주는 추가 신뢰 보너스
    "unrelated_domain_penalty": -60,  # 공식 도메인도 아니고 서비스명과 관련도 없을 때
    "canonical_domain_bonus": 30,     # www.서비스.com / 서비스.com 같은 대표 도메인
    "different_product_subdomain_penalty": -50,  # kids./business./ads. 등 아예 다른 제품/서비스
    "support_subdomain_penalty": -50,  # help./support. 등 고객지원 포털이면서 terms 증거가 없을 때만 적용
    "news_article_penalty": -60,      # 뉴스 기사로 판단될 때
    "reporter_mention_penalty": -80,  # '~~ 기자' 언급이 있을 때 (뉴스 강력 신호)
    "title_keyword_bonus": 10,        # 제목에 terms/약관 키워드가 있을 때
}

# 본 서비스와는 "완전히 다른 제품/사업"으로 볼 수 있는 서브도메인.
# 예: kids.youtube.com(별도 앱), ads.xxx.com, business.xxx.com 등은 terms 경로가 있어도
# 그 안의 약관은 본 서비스가 아닌 그 하위 제품 자체의 약관일 가능성이 높아 항상 감점합니다.
DIFFERENT_PRODUCT_SUBDOMAIN_PREFIXES = [
    "kids.", "ads.", "business.", "store.", "shop.",
    "developers.", "dev.", "music.", "tv.", "gaming.",
]

# 본 서비스의 "고객지원/정보 포털"로 보이는 서브도메인.
# help.netflix.com/legal/termsofuse처럼 법적 문서를 이 서브도메인에 정식으로 호스팅하는
# 회사도 많기 때문에, terms/legal 관련 강한 증거(경로 또는 본문)가 있으면 감점하지 않고
# 증거가 없는 일반 FAQ성 페이지일 때만 감점합니다.
SUPPORT_SUBDOMAIN_PREFIXES = [
    "help.", "support.", "blog.", "careers.", "jobs.",
    "news.", "community.", "forum.", "status.",
]

# 하위 호환을 위해 canonical 판별에는 두 그룹을 합쳐서 사용
NON_PRIMARY_SUBDOMAIN_PREFIXES = DIFFERENT_PRODUCT_SUBDOMAIN_PREFIXES + SUPPORT_SUBDOMAIN_PREFIXES

def is_canonical_domain(url, service_name):
    """host가 서비스의 '대표 도메인'(www.서비스.com 또는 서비스.com)인지 판별.
    kids.youtube.com처럼 서비스명이 포함되지만 별도 하위 서비스인 서브도메인은 제외한다."""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    if not host:
        return False
    # www. 접두어는 대표 도메인으로 인정
    bare_host = host[4:] if host.startswith('www.') else host
    labels = bare_host.split('.')
    # 대표 도메인은 보통 "서비스.tld" 또는 "서비스.co.kr" 형태로 라벨이 2~3개 정도
    is_root_like = len(labels) <= 3
    if not is_root_like:
        return False
    if any(bare_host.startswith(p) for p in NON_PRIMARY_SUBDOMAIN_PREFIXES):
        return False
    return True

def is_different_product_subdomain(host):
    return any(host.startswith(p) or f".{p}" in host for p in DIFFERENT_PRODUCT_SUBDOMAIN_PREFIXES)


def is_support_subdomain(host):
    return any(host.startswith(p) or f".{p}" in host for p in SUPPORT_SUBDOMAIN_PREFIXES)


def compute_score(service_name, r, check_relevance=True, with_reasons=False):
    """후보 검색결과 r에 대한 점수를 계산합니다.

    Args:
        check_relevance: True면 공식 도메인이 아니고 서비스명과도 무관할 때 감점(unrelated_domain_penalty)을 적용합니다.
            select_best_result의 폴백 단계(모든 후보가 관련성 부족으로 제외됐을 때)에서는
            False로 호출해 감점을 건너뛰고 재시도합니다.
        with_reasons: True면 (score, reasons) 튜플을 반환합니다. reasons는 "항목: 부호점수" 문자열 리스트.

    Returns:
        score(int) 또는 (score, reasons). 앱스토어/블로그 등 즉시 제외 대상이면 (None 또는 (None, reasons)).
    """
    url = r.get('url') or ''
    title = (r.get('title') or '').lower()
    snippet = (r.get('content') or '')
    host = urlparse(url).netloc.lower()

    reasons = []

    def add(key):
        nonlocal score
        points = SCORE_WEIGHTS[key]
        score += points
        reasons.append(f"{key}: {points:+d}")

    # 앱스토어 / 플레이스토어 / 네이버 블로그 즉시 제외
    if any(p in host for p in PLATFORM_DOMAINS):
        logging.info(f"Excluding platform/blog candidate: {url}")
        return (None, ["excluded: platform/store domain"]) if with_reasons else None

    score = 0
    has_path_terms = url_path_has_terms(url)
    has_content_terms = content_looks_like_terms(snippet)

    if has_path_terms:
        add("path_or_query_terms")
    if has_content_terms:
        add("content_terms")

    path = urlparse(url).path or '/'
    if path in ('/', ''):
        add("root_path_penalty")

    if domain_is_blacklisted(url):
        add("blacklisted_domain")

    if is_official_domain(url, service_name):
        if has_path_terms or has_content_terms:
            add("official_domain_bonus")
    elif check_relevance and not host_related(url, service_name):
        add("unrelated_domain_penalty")

    # 대표 도메인(www.서비스.com 등)은 우대.
    # kids./ads. 같은 '완전히 다른 제품' 서브도메인은 terms 증거 유무와 무관하게 항상 감점.
    # help./support. 같은 '고객지원 포털' 서브도메인은 terms/legal 증거가 없을 때만 감점
    # (Netflix처럼 help.netflix.com/legal/termsofuse가 정식 약관 위치인 경우가 있기 때문).
    if is_canonical_domain(url, service_name):
        add("canonical_domain_bonus")
    elif is_different_product_subdomain(host):
        add("different_product_subdomain_penalty")
    elif is_support_subdomain(host) and not (has_path_terms or has_content_terms):
        add("support_subdomain_penalty")

    try:
        if is_news_article(snippet, url):
            add("news_article_penalty")
        if count_reporter_mentions(snippet) >= 1:
            add("reporter_mention_penalty")
    except Exception:
        pass

    if any(k in title for k in ['terms', '이용약관', '약관', 'terms of service', 'terms & conditions']):
        add("title_keyword_bonus")

    return (score, reasons) if with_reasons else score

def select_best_result(service_name, search_results, allow_manual_selection=True):
    if not search_results:
        return None
    # 1차: 관련성 체크(check_relevance=True)를 포함한 정상 스코어링
    scored = []
    for i, r in enumerate(search_results):
        score = compute_score(service_name, r)
        if score is None:
            # None indicates candidate was excluded (e.g., platform)
            continue
        scored.append((score, i, r))

    scored.sort(reverse=True, key=lambda x: x[0])

    # 후보가 모두 제외되어 비어있다면, 관련성 체크(host_related)만 건너뛰고 재시도
    # (다른 감점/보너스 항목은 그대로 유지 — compute_score를 재사용해 로직 중복을 없앰)
    if not scored:
        logging.info('All candidates excluded by host_related; falling back to relevance-relaxed scoring')
        for i, r in enumerate(search_results):
            score = compute_score(service_name, r, check_relevance=False)
            if score is None:
                continue
            scored.append((score, i, r))

    scored.sort(reverse=True, key=lambda x: x[0])

    # 자동 선정: 점수만으로는 선정하지 않음 — 반드시 본문 증거(content_looks_like_terms) 필요
    # 엄격 모드: 자동으로 선정하려면 '경로 또는 본문' 증거가 반드시 있어야 함
    filtered = [s for s in scored if (url_path_has_terms(s[2].get('url','')) or content_looks_like_terms(s[2].get('content','')))]
    if filtered:
        # 증거 있는 후보 중 최고 점수 반환
        filtered.sort(reverse=True, key=lambda x: x[0])
        return filtered[0][2]

    # 증거가 전혀 없으면 — 우선 상위 몇개 후보에 대해 실제 본문을 추출하여 검사
    # 후보 검사 수를 10개로 늘림
    top_candidates = [r for _, _, r in scored[:10]]
    for cand in top_candidates:
        try:
            raw = extract_raw_tos(cand.get('url'))
            # 기사/뉴스로 판단되면 건너뜀
            if is_news_article(raw, cand.get('url')):
                continue
            if raw and content_looks_like_terms(raw):
                return cand
        except Exception:
            continue

    # 증거가 전혀 없으면, 먼저 OpenAI 폴백으로 자동 정렬 시도
    listing = ""
    for i, r in enumerate(search_results):
        listing += (
            f"[{i}] URL: {r.get('url')}\n"
            f"제목: {r.get('title')}\n"
            f"내용 일부: {r.get('content', '')[:300]}\n\n"
        )

    system_prompt = SYSTEM_PROMPT_TEMPLATE
    user_prompt = USER_PROMPT_TEMPLATE.format(service_name=service_name, listing=listing)

    # OpenAI 폴백은 키가 있을 때만 시도
    if openai_client:
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )

            result = json.loads(response.choices[0].message.content)
            ranked = result.get("ranked_indices", [])
            if ranked:
                idx = ranked[0]
                if 0 <= idx < len(search_results):
                    return search_results[idx]
        except Exception:
            pass

    if not allow_manual_selection:
        return None

    # 그래도 없으면 사용자에게 후보를 보여줘서 수동 선택하게 함
    print("자동 필터로는 확실한 약관 페이지를 찾지 못했습니다. 아래 후보에서 선택하세요:")
    for score, i, r in scored[:5]:
        print(f"[{i}] {r.get('url')} (score={score})")

    while True:
        choice = input("선택할 인덱스 번호 입력(취소하려면 q): ").strip()
        if choice.lower() == 'q':
            return None
        if not choice.isdigit():
            print("숫자 인덱스를 입력하세요.")
            continue
        idx = int(choice)
        if 0 <= idx < len(search_results):
            return search_results[idx]
        print("유효한 인덱스가 아닙니다.")

def extract_raw_tos(url):
    # 우선 Tavily에서 시도하되, 언제나 Playwright 심화 추출을 빠르게 시도하여 더 완전한 본문 확보
    try:
        # 먼저 Tavily 추출 시도
        response = tavily_client.extract(urls=[url])
        results = response.get("results", [])
    except Exception:
        results = []

    # PDF인 경우 직접 다운로드해 텍스트 추출을 시도
    def is_pdf_link(u):
        return u and (u.lower().endswith('.pdf') or 'pdf' in u.lower())

    def extract_pdf_text(u):
        try:
            r = requests.get(u, stream=True, timeout=20)
            r.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tf:
                for chunk in r.iter_content(8192):
                    tf.write(chunk)
                tmpname = tf.name
            reader = PdfReader(tmpname)
            texts = []
            for p in reader.pages:
                try:
                    texts.append(p.extract_text() or '')
                except Exception:
                    continue
            return '\n\n'.join(texts).strip()
        except Exception:
            return None

    # PDF 링크면 Playwright로 가기 전에 바로 PDF를 다운로드해 텍스트 추출
    if is_pdf_link(url):
        pdf_text = extract_pdf_text(url)
        if pdf_text and len(pdf_text) > 200:
            return pdf_text

    # 항상 Playwright deep 추출을 병렬적으로 또는 직후 우선 시도
    try:
        deep_attempt = render_and_extract_deep(url)
    except Exception:
        deep_attempt = None

    if not results:
        return deep_attempt
    # tavily가 반환한 최종 URL이 원 후보 도메인과 다른 경우에도, 일부 사이트는 리다이렉트로 본문을 제공하므로
    # 호스트 불일치로 바로 거부하지 않도록 변경합니다. (과거에는 일부 공지/도메인이 리다이렉트되어 누락됨)

    raw = results[0].get("raw_content")
    # PDF 후보일 경우 직접 추출 우선
    candidate_url = results[0].get('url') if results else url
    if is_pdf_link(candidate_url):
        pdf_text = extract_pdf_text(candidate_url)
        if pdf_text and len(pdf_text) > 200:
            return pdf_text

    # 우선: deep_attempt이 충분하면 그것을 사용
    if deep_attempt and len(deep_attempt) >= 2000:
        return deep_attempt

    if raw and len(raw) >= 2000:
        return raw

    # Tavily raw가 짧다면, deep를 시도한 뒤 없으면 기존 렌더러
    if deep_attempt:
        return deep_attempt
    try:
        return render_and_extract(results[0].get('url'))
    except Exception:
        return raw or None

def render_and_extract(url):
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=20000)
                page.wait_for_timeout(1500)
                text = page.inner_text('body')
                return text
        except Exception as e:
            logging.exception(f"render_and_extract failed (attempt {attempt}) for {url}: {e}")
            if attempt < max_attempts:
                time.sleep(1)
                continue
            raise
def render_and_extract_deep(url, max_links=12, min_length=1500):
    """Playwright로 페이지 렌더 후 내부 링크를 추출해 약관으로 보이는 링크들을 우선 방문해 본문을 수집합니다.
    반환값: 텍스트(str) 또는 None
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, timeout=30000)
                page.wait_for_timeout(1500)
                body = page.inner_text('body')

                # 초기 body가 충분하면 일단 수집
                candidates = []
                if body and len(body) >= min_length and content_looks_like_terms(body):
                    return body

                # 링크 수집
                anchors = page.query_selector_all('a[href]')
                hrefs = []
                for a in anchors:
                    try:
                        h = a.get_attribute('href')
                        if not h:
                            continue
                        # normalize absolute URLs
                        if h.startswith('/'):
                            base = urlparse(url)
                            h = f"{base.scheme}://{base.netloc}{h}"
                        if h.startswith('http'):
                            hrefs.append(h)
                    except Exception:
                        continue

                # 후보 링크 중에 약관/terms 관련 키워드가 있는 것 우선
                prioritized = [h for h in hrefs if re.search(r'(terms|약관|policy|legal|usage)', h, re.I)]
                others = [h for h in hrefs if h not in prioritized]
                try_list = prioritized + others[:max(0, max_links - len(prioritized))]

                for h in try_list[:max_links]:
                    try:
                        page.goto(h, timeout=25000)
                        page.wait_for_timeout(1000)
                        txt = page.inner_text('body')
                        if not txt:
                            continue
                        if content_looks_like_terms(txt):
                            return txt
                        candidates.append((len(txt), txt, h))
                    except Exception:
                        continue

                # 후보 중 길이가 가장 긴 것 반환
                if candidates:
                    candidates.sort(reverse=True, key=lambda x: x[0])
                    return candidates[0][1]
            finally:
                browser.close()
    except Exception as e:
        logging.exception(f"render_and_extract_deep failed for {url}: {e}")
    return None

def save_tos_to_file(service_name, content):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    # RAG/terms/<서비스명>/terms.txt 형태로 저장
    terms_dir = os.path.join(base_dir, "RAG", "terms")

    def has_korean(text):
        return bool(re.search(r'[\uac00-\ud7a3]', text))

    def extract_ascii_text(text):
        tokens = re.findall(r'[A-Za-z0-9]+', text)
        return ' '.join(tokens).strip()

    def canonicalize_service_name(name):
        name = unicodedata.normalize('NFKC', name).strip()
        if not name:
            return 'untitled'
        if has_korean(name):
            ascii_part = extract_ascii_text(name)
            if ascii_part:
                return ascii_part
        return name

    def make_safe_name(name, max_len=100):
        name = unicodedata.normalize('NFKC', name)
        name = name.lower()
        name = re.sub(r'[^0-9a-z\-\_가-힣]+', '_', name)
        name = re.sub(r'_+', '_', name).strip('_')
        if len(name) > max_len:
            name = name[:max_len]
        if not name:
            name = 'untitled'
        return name

    canonical_name = canonicalize_service_name(service_name)
    safe_name = make_safe_name(canonical_name)

    # 서비스명 폴더 생성: RAG/terms/<서비스명>/
    service_dir = os.path.join(terms_dir, safe_name)
    os.makedirs(service_dir, exist_ok=True)

    file_path = os.path.join(service_dir, "terms.txt")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path


def prepare_crawler():
    ensure_api_keys()
    ensure_playwright_installed()


def main():
    prepare_crawler()
    service_name = get_service_name()
    list_mode = False
    if service_name.endswith(" --list"):
        list_mode = True
        service_name = service_name.replace(" --list", "").strip()
    print(f"'{service_name}' 약관 검색 중...")

    search_results = search_tos(service_name)
    if not search_results:
        print("검색 결과가 없습니다.")
        return

    if list_mode:
        print("상위 후보 목록 (링크 — 점수, 점수순):\n")
        scored_list = []
        for i, r in enumerate(search_results):
            score, reasons = compute_score(service_name, r, with_reasons=True)
            if score is None:
                continue
            scored_list.append((score, i, r, reasons))
        # 점수 내림차순 정렬
        scored_list.sort(reverse=True, key=lambda x: x[0])
        for score, i, r, reasons in scored_list:
            url = r.get('url')
            print(f"[{i}] {url} — {score}")
            for reason in reasons:
                print(f"      · {reason}")
        return

    best = select_best_result(service_name, search_results)
    if best is None:
        print("조건에 맞는 공식 약관 페이지를 찾지 못했습니다.")
        return

    print(f"선택된 URL: {best['url']}")

    raw_content = extract_raw_tos(best["url"])
    if not raw_content:
        print("본문 추출에 실패했습니다.")
        return

    # 별도 필터링 없이 추출된 원문을 그대로 파일에 저장합니다.
    file_path = save_tos_to_file(service_name, raw_content)
    print(f"저장 완료: {file_path}")


if __name__ == "__main__":
    main()