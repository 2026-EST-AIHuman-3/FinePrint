"""
1. 라이브러리 다운로드
pip install tavily-python openai

2. 설정
conda activate fineprint311
cd /smhrd2/FinePrint/jhc

3. 환경변수 등록
export TAVILY_API_KEY="YOUR_TAVILY_API_KEY"
export OPENAI_API_KEY="YOUR_OPENAI_API_KEY"

4. 실행
python tavily_test3-1.py
"""

import os
import json
from tavily import TavilyClient
from openai import OpenAI
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
import logging
import time
import re
import unicodedata
from dotenv import load_dotenv

load_dotenv()

# 1. API 키 등록
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def ensure_api_keys():
    missing = []
    if not TAVILY_API_KEY:
        missing.append('TAVILY_API_KEY')
    if not OPENAI_API_KEY:
        missing.append('OPENAI_API_KEY')
    if missing:
        print('필수 환경변수가 설정되어 있지 않습니다: ' + ', '.join(missing))
        print('예시로 아래 명령을 쉘에 붙여넣어 설정하세요:')
        print('export TAVILY_API_KEY="your_tavily_api_key_here"')
        print('export OPENAI_API_KEY="your_openai_api_key_here"')
        raise SystemExit(1)

ensure_api_keys()

tavily_client = TavilyClient(api_key=TAVILY_API_KEY)
openai_client = None
if OPENAI_API_KEY:
    try:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        openai_client = None

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

ensure_playwright_installed()

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
    "blog", "medium.com", "wordpress.com", "tistory.com", "naver.com", "brunch.co.kr",
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
PLATFORM_DOMAINS = ["apps.apple.com", "play.google.com", "blog.naver.com"]

def get_service_name():
    return input("구독형 서비스명을 입력하세요: ").strip()

def search_tos(service_name, max_results=10):
    query = f"{service_name} 약관 OR {service_name} terms of service"
    response = tavily_client.search(
        query=query,
        search_depth="advanced",
        max_results=max_results,
        include_raw_content=False,
    )
    return response.get("results", [])

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
    path = urlparse(url).path.lower()
    return any(k in path for k in TERMS_PATH_KEYWORDS)

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
    import re
    reporter_mentions = len(re.findall(r"[\w가-힣]{1,20}\s*기자", content)) + len(re.findall(r"기자[\s,，。.]", content))
    # 기사 키워드 2개 이상 또는 기자 언급이 1회 이상이면 뉴스로 판단
    return score >= 2 or reporter_mentions >= 1

def count_reporter_mentions(content):
    if not content:
        return 0
    import re
    return len(re.findall(r"[\w가-힣]{1,20}\s*기자", content)) + len(re.findall(r"기자[\s,，。.]", content))

def domain_is_blacklisted(url):
    host = urlparse(url).netloc.lower()
    if any(b in host for b in SITE_TYPE_BLACKLIST):
        return True
    # 집계/요약 도메인 키워드 배제
    if any(k in host for k in AGGREGATOR_HOST_KEYWORDS):
        return True
    return False

def select_best_result(service_name, search_results):
    if not search_results:
        return None

    # 1) 후보 스코어링: 우선순위 - 공식 도메인, URL 패턴, 본문 성격, 블랙리스트 점수 감점
    scored = []
    for i, r in enumerate(search_results):
        url = r.get('url') or ''
        title = (r.get('title') or '').lower()
        snippet = (r.get('content') or '')

        score = 0
        host = urlparse(url).netloc.lower()
        # 앱스토어 / 플레이스토어 / 네이버 블로그 즉시 제외
        low_url = url.lower()
        if any(p in host for p in PLATFORM_DOMAINS) or any(p in low_url for p in PLATFORM_DOMAINS):
            logging.info(f"Excluding platform/blog candidate: {url}")
            continue
        # 도메인이 서비스명과 무관하면 후보에서 제외
        try:
            if not host_related(url, service_name):
                logging.info(f"Excluding candidate (domain unrelated): {url}")
                continue
        except Exception:
            pass
        # 공식 도메인 가중치 제거: 경로와 본문 증거 위주로 판단
        has_path_terms = url_path_has_terms(url)
        has_content_terms = content_looks_like_terms(snippet)
        if has_path_terms:
            score += 40
        if has_content_terms:
            score += 30
        # 루트('/') URL(메인 페이지)은 감점
        path = urlparse(url).path or '/'
        if path == '/' or path == '':
            score -= 40
        if domain_is_blacklisted(url):
            score -= 40
        # 서비스명과 도메인이 무관하면 강한 감점
        try:
            if not host_related(url, service_name):
                score -= 60
        except Exception:
            pass
        # 스니펫 수준에서 기자/뉴스 지표가 보이면 강하게 감점
        try:
            if is_news_article(snippet, url):
                # 기본 뉴스 감점
                score -= 60
            # 기자 언급이 보이면 추가 강한 감점
            rep_count = count_reporter_mentions(snippet)
            if rep_count >= 1:
                score -= 80
        except Exception:
            pass

        # 약간의 가중치: 제목에 terms 약관 명시
        if any(k in title for k in ['terms', '이용약관', '약관', 'terms of service', 'terms & conditions']):
            score += 10

        scored.append((score, i, r))

    scored.sort(reverse=True, key=lambda x: x[0])

    # 후보가 모두 제외되어 비어있다면, 관련성 체크를 무시하고 기본 스코어링으로 재시도
    if not scored:
        logging.info('All candidates excluded by host_related; falling back to unfiltered scoring')
        for i, r in enumerate(search_results):
            url = r.get('url') or ''
            title = (r.get('title') or '').lower()
            snippet = (r.get('content') or '')
            score = 0
            if url_path_has_terms(url):
                score += 40
            if content_looks_like_terms(snippet):
                score += 30
            path = urlparse(url).path or '/'
            if path == '/' or path == '':
                score -= 40
            if domain_is_blacklisted(url):
                score -= 40
            if is_news_article(snippet, url):
                score -= 60
            rep_count = count_reporter_mentions(snippet)
            if rep_count >= 1:
                score -= 80
            if any(k in title for k in ['terms', '이용약관', '약관', 'terms of service', 'terms & conditions']):
                score += 10
            scored.append((score, i, r))

    scored.sort(reverse=True, key=lambda x: x[0])

    # 자동 선정: 점수만으로는 선정하지 않음 — 반드시 본문 증거(content_looks_like_terms) 필요
    top_score, top_idx, top_r = scored[0]

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

    # 증거가 전혀 없으면 자동 선택을 하지 않고 사용자에게 후보를 보여줌
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

    # 그렇지 않으면 OpenAI 판별기(원래 플로우)로 폴백
    listing = ""
    for i, r in enumerate(search_results):
        listing += (
            f"[{i}] URL: {r.get('url')}\n"
            f"제목: {r.get('title')}\n"
            f"내용 일부: {r.get('content', '')[:300]}\n\n"
        )

    system_prompt = """
    너는 구독형 서비스의 '이용약관 원문 페이지'만을 정확히 골라내는 판별기다.
    아래 검색 결과 목록을 검토하여, 진짜 이용약관 원문일 가능성이 높은 순서대로 정렬하라.
    [출력 규칙]
    반드시 아래 JSON 형식으로만 답하라.
    {"ranked_indices": [<가능성이 높은 순서대로 나열한 번호들>]}
    """

    user_prompt = f"서비스명: {service_name}\n\n검색 결과 목록:\n{listing}"

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

    # 최후의 수단: 점수 기준 상위 반환
    return top_r

def extract_raw_tos(url):
    response = tavily_client.extract(urls=[url])
    results = response.get("results", [])
    if not results:
        # tavily 못가져오면 Playwright로 렌더링 시도
        try:
            return render_and_extract(url)
        except Exception:
            return None
    # tavily가 반환한 최종 URL이 원 후보 도메인과 다른 경우 후보로 부적합 처리
    candidate_url = results[0].get('url')
    try:
        orig_host = urlparse(url).netloc.lower()
        cand_host = urlparse(candidate_url).netloc.lower() if candidate_url else ''
        if cand_host and orig_host and cand_host != orig_host:
            logging.info(f"extract_raw_tos: candidate redirected to different host {candidate_url} (orig {url}), rejecting")
            return None
    except Exception:
        pass

    raw = results[0].get("raw_content")
    if raw:
        return raw
    # 빈 경우 Playwright로 렌더링 시도
    try:
        return render_and_extract(results[0].get('url'))
    except Exception:
        return None

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
        finally:
            try:
                browser.close()
            except Exception:
                pass

def save_tos_to_file(service_name, content):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    def make_safe_name(name, max_len=100, keep_korean=True):
        # 정규화
        name = unicodedata.normalize('NFKC', name)
        if not keep_korean:
            name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
        # 소문자
        name = name.lower()
        # 불허 문자 -> 언더스코어
        name = re.sub(r'[^0-9a-z\-\_가-힣]+', '_', name)
        name = re.sub(r'_+', '_', name).strip('_')
        if len(name) > max_len:
            name = name[:max_len]
        if not name:
            name = 'untitled'
        return name

    safe_name = make_safe_name(service_name)
    file_path = os.path.join(data_dir, f"{safe_name}_이용약관.txt")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return file_path

def main():
    service_name = get_service_name()
    print(f"'{service_name}' 약관 검색 중...")

    search_results = search_tos(service_name)
    if not search_results:
        print("검색 결과가 없습니다.")
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

    file_path = save_tos_to_file(service_name, raw_content)
    print(f"저장 완료: {file_path}")


if __name__ == "__main__":
    main()
