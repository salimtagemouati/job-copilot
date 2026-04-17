"""
Tavily-powered job search and company research — MODULE 2b (ingestion).

Used for:
1. Proactive job searching by market
2. Company research for interview prep context
3. Fetching JD from URL when user provides a link
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tavily import TavilyClient

from config import settings
from models.schemas import Market
from utils.logger import get_logger

logger = get_logger(__name__)

# Singleton client
_client: TavilyClient | None = None


def get_tavily() -> TavilyClient:
    """Returns shared Tavily client."""
    global _client
    if _client is None:
        _client = TavilyClient(api_key=settings.tavily_api_key)
    return _client


# ── Market-aware search query templates ───────────────────────────────────────
_MARKET_QUERIES = {
    Market.morocco: [
        "AI Engineer junior Casablanca Rabat Morocco",
        "ML Engineer Python FastAPI Morocco remote",
        "Junior Data Scientist Morocco Casablanca Rabat",
        "Backend Engineer Python Morocco 2024 2025",
    ],
    Market.germany: [
        "Junior AI Engineer Berlin Munich English speaking visa sponsorship",
        "ML Engineer Berlin international team English working language",
        "Python AI Developer Germany English relocation support Blue Card",
        "Junior Data Scientist Munich English speaking team junior",
    ],
    Market.canada: [
        "ML Engineer Montreal junior LMIA work permit sponsorship",
        "AI Engineer Toronto open to international applicants",
        "Python Developer Montreal AI startup work permit sponsorship 2025",
    ],
    Market.remote: [
        "Junior AI Engineer remote worldwide international contractors",
        "LLM Engineer remote EU US worldwide open international",
        "GenAI developer fully remote worldwide English",
    ],
}


def search_jobs(query: str, market: Market, max_results: int = 5) -> list[str]:
    """
    Searches for jobs using Tavily and returns raw JD texts.

    Args:
        query: Custom search query (or use market-default queries if empty)
        market: Target market for query tuning
        max_results: Max number of results to return

    Returns:
        List of raw JD texts extracted from search results.
        Falls back to empty list (logs warning) if Tavily fails.

    Example:
        >>> jds = search_jobs("Junior AI Engineer", Market.morocco)
        >>> for jd in jds:
        ...     job = parse_job(jd)
    """
    client = get_tavily()
    results_text: list[str] = []

    # Use provided query or pick market-default
    queries_to_run = [query] if query.strip() else _MARKET_QUERIES.get(market, [query])

    for q in queries_to_run[:2]:  # cap at 2 queries to limit API usage
        try:
            logger.info(f"[tavily] Searching: '{q}'")
            response = client.search(
                query=q,
                search_depth="advanced",
                max_results=max_results,
                include_raw_content=True,
            )

            for result in response.get("results", []):
                # Prefer raw_content, fall back to content snippet
                content = result.get("raw_content") or result.get("content", "")
                url = result.get("url", "")
                title = result.get("title", "")

                if content and len(content) > 200:  # skip stub results
                    # Prepend metadata for parser context
                    full_text = f"SOURCE: {url}\nTITLE: {title}\n\n{content}"
                    results_text.append(full_text)
                    logger.info(f"[tavily] Got result: {title[:60]}... ({len(content)} chars)")

        except Exception as e:
            logger.warning(f"[tavily] Search failed for '{q}': {e}")
            continue

    logger.info(f"[tavily] Returned {len(results_text)} usable JD texts")
    return results_text


def fetch_job_from_url(url: str) -> str | None:
    """
    Fetches the content of a job posting URL using Tavily extract.

    Args:
        url: Direct URL to a job posting

    Returns:
        Raw text content of the page, or None if fetch fails

    Example:
        >>> text = fetch_job_from_url("https://jobs.lever.co/company/job-id")
        >>> if text:
        ...     job = parse_job(text, source_url=url)
    """
    client = get_tavily()
    try:
        logger.info(f"[tavily] Fetching URL: {url}")
        response = client.extract(urls=[url])
        results = response.get("results", [])
        if results:
            content = results[0].get("raw_content", "")
            logger.info(f"[tavily] Fetched {len(content)} chars from {url}")
            return content if content else None
        logger.warning(f"[tavily] No content returned from {url}")
        return None
    except Exception as e:
        logger.warning(f"[tavily] URL fetch failed for {url}: {e}")
        return None


def get_company_research(company: str, role: str) -> str:
    """
    Fetches recent company context for interview prep.

    Searches for: funding news, tech blog, engineering culture, recent news.

    Args:
        company: Company name to research
        role: Role being applied for (adds context to query)

    Returns:
        String summary of company context (2-4 paragraphs),
        or empty string if Tavily fails.

    Example:
        >>> research = get_company_research("Zalando", "ML Engineer")
        >>> print(research[:200])
    """
    client = get_tavily()
    queries = [
        f"{company} engineering culture tech stack 2024 2025",
        f"{company} funding news product 2024 2025",
        f"{company} {role} team interview process",
    ]

    snippets: list[str] = []

    for q in queries[:2]:  # cap at 2 queries
        try:
            logger.info(f"[tavily] Company research: '{q}'")
            response = client.search(
                query=q,
                search_depth="basic",
                max_results=3,
            )
            for result in response.get("results", []):
                content = result.get("content", "").strip()
                title = result.get("title", "")
                url = result.get("url", "")
                if content and len(content) > 100:
                    snippets.append(f"[{title}] ({url})\n{content}")
        except Exception as e:
            logger.warning(f"[tavily] Company research failed for '{q}': {e}")
            continue

    if not snippets:
        logger.warning(f"[tavily] No company research found for {company}")
        return ""

    combined = "\n\n".join(snippets[:4])  # top 4 snippets
    logger.info(f"[tavily] Company research: {len(combined)} chars for {company}")
    return combined


if __name__ == "__main__":
    print("Testing Tavily company research...")
    try:
        research = get_company_research("Zalando", "ML Engineer")
        if research:
            print(f"✅ Got {len(research)} chars of research")
            print(research[:400])
        else:
            print("⚠️  No research results (check API key)")
    except Exception as e:
        print(f"❌ Tavily failed: {e}")

    print("\nTesting Tavily job search...")
    try:
        results = search_jobs("Junior AI Engineer Python", Market.morocco, max_results=2)
        print(f"✅ Got {len(results)} job results")
        for i, r in enumerate(results):
            print(f"  Result {i+1}: {r[:100]}...")
    except Exception as e:
        print(f"❌ Job search failed: {e}")
