import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
from datetime import datetime


# Headers to mimic a real browser and avoid being blocked by websites
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/117.0.0.0 Safari/537.36"
    )
}

class Website:
    """
    A utility class to represent a Website that we have scraped,
    with methods to extract and normalize visible text and hyperlinks.

    This class fetches HTML content from a given URL, parses it using BeautifulSoup,
    and extracts the title, visible text content, and all hyperlinks found on the page.
    """

    def __init__(self, url: str, timeout: int = 10):
        """
        Initialize the Website object by fetching and parsing the given URL.

        Args:
            url (str): The URL to scrape
            timeout (int): Request timeout in seconds (default: 10)
        """
        self.url = url
        self.text = ""
        self.title = ""
        self.links = []
        self.published_at = None  # ISO 8601 string if found, else None

        try:
            # Fetch the webpage with custom headers to avoid blocking
            response = requests.get(url, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
        except Exception as e:
            logging.error(f"Failed to fetch {url}: {e}")
            return

        # Only process HTML content, skip other file types
        content_type = response.headers.get("Content-Type", "")
        if "html" not in content_type:
            logging.warning(f"Skipped non-HTML content: {content_type}")
            return

        self.body = response.content
        self._parse() # Parse the HTML content

    def _extract_article_text(self, soup: BeautifulSoup) -> str:
        """
        Prefer <article> or common 'article body' containers.
        Extract only ["p", "h1", "h2", "h3", "h4", "li"] text; strip typical non-content blocks.
        Fallback: the div/section with the most <p> text.
        """

        def clean_and_join(node):
            for t in node(["script", "style", "noscript", "aside", "figure", "figcaption", "input", "img", "nav", "header", "footer"]):
                t.decompose()
            parts = [el.get_text(" ", strip=True)
                     for el in node.find_all(["p", "h1", "h2", "h3", "h4", "li"])
                     if el.get_text(strip=True)]
            return "\n\n".join(parts)

        # 1) Direct <article>
        article = soup.find("article")
        if article:
            txt = clean_and_join(article)
            if txt:
                return txt

        # 2) Common CMS selectors
        for sel in [
            '[itemprop="articleBody"]',
            ".article-body", ".article__body", ".entry-content", ".post-content",
            ".content__article-body", ".story-body", ".article-content", ".news-content",
            ".td-post-content", ".post-body", ".content-body", ".body-content"
        ]:
            node = soup.select_one(sel)
            if node:
                txt = clean_and_join(node)
                if txt:
                    return txt

        # 3) Fallback: pick the container with the most <p> text
        best_text, best_len = "", 0
        for container in soup.find_all(["div", "section", "main"]):
            ps = [p.get_text(" ", strip=True) for p in container.find_all("p")]
            text = "\n\n".join([t for t in ps if t])
            if len(text) > best_len:
                best_text, best_len = text, len(text)

        return best_text

    def _maybe_parse_date(self, raw):
        """Best-effort parse -> YYYY-MM-DD (date only)."""
        if not raw:
            return None
        s = str(raw).strip()

        # Normalize trailing Z to +00:00 so fromisoformat works
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"

        # Try ISO first
        try:
            dt = datetime.fromisoformat(s)
            return dt.date().isoformat()  # <-- only date
        except Exception:
            pass

        # Try a few common patterns
        fmts = [
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y",
        ]
        for fmt in fmts:
            try:
                dt = datetime.strptime(s, fmt)
                return dt.date().isoformat()  # <-- only date
            except Exception:
                continue

        return None

    def _extract_published_at(self, soup):
        """
        Return publication datetime as ISO 8601 string if found, else None.
        Priority: JSON-LD -> meta tags -> <time datetime>.
        """
        # 1) JSON-LD blocks (NewsArticle/Article)
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except Exception:
                continue

            # Handle dict, list, and @graph
            candidates = []
            if isinstance(data, dict):
                candidates = [data] + (data.get("@graph") or [])
            elif isinstance(data, list):
                candidates = data

            for obj in candidates:
                if not isinstance(obj, dict):
                    continue
                typ = obj.get("@type", "")
                if isinstance(typ, list):
                    typ = " ".join(typ)
                if "Article" in str(typ) or "NewsArticle" in str(typ) or "BlogPosting" in str(typ):
                    iso = self._maybe_parse_date(obj.get("datePublished"))
                    if iso:
                        return iso

        # 2) Meta tags
        meta_queries = [
            {"property": "article:published_time"},
            {"name": "article:published_time"},
            {"itemprop": "datePublished"},
            {"name": "pubdate"},
            {"name": "publication_date"},
            {"name": "date"},
        ]
        for attrs in meta_queries:
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                iso = self._maybe_parse_date(tag.get("content"))
                if iso:
                    return iso

        # 3) <time datetime="...">
        t = soup.find("time", attrs={"datetime": True})
        if t:
            iso = self._maybe_parse_date(t.get("datetime"))
            if iso:
                return iso

        # (Optional future: site-specific heuristics)
        return None

    def _parse(self):
        """
        Parse the HTML content using BeautifulSoup to extract title, text, and links.

        This method:
        1. Extracts the page title
        2. Removes unwanted elements (scripts, styles, images, inputs)
        3. Extracts visible text content
        4. Finds and normalizes all hyperlinks
        """
        soup = BeautifulSoup(self.body, "html.parser")

        # Extract page title, handle cases where title tag doesn't exist
        self.title = soup.title.string.strip() if soup.title else "No title found"

        # Extract visible text content from body
        if soup.body:
            # still prune obvious junk at body level (cheap win)
            for tag in soup.body(["script", "style", "noscript"]):
                tag.decompose()
            # NEW: aim at article content instead of whole body
            extracted = self._extract_article_text(soup)
            self.text = extracted if extracted else ""
        else:
            self.text = ""

        # Find all anchor tags with href attributes and normalize the links
        raw_links = soup.find_all("a", href=True)
        self.links = self._normalize_links([a.get("href") for a in raw_links])

        self.published_at = self._extract_published_at(soup)

    def _normalize_links(self, hrefs):
        """
        Clean and normalize a list of href attributes into absolute URLs.

        Args:
            hrefs (list): List of href strings from anchor tags

        Returns:
            list: List of clean, absolute URLs

        This method:
        1. Removes empty, fragment (#), and javascript: links
        2. Converts relative URLs to absolute URLs using urljoin
        3. Returns a clean list of valid URLs
        """
        clean_links = []
        for href in hrefs:
            href = href.strip()

            # Skip empty links, fragment links, and javascript links
            if not href or href.startswith("#") or href.lower().startswith("javascript"):
                continue

            # Convert relative URLs to absolute URLs
            full_url = urljoin(self.url, href)
            clean_links.append(full_url)
        return clean_links

    def get_contents(self):
        """
        Get the formatted content of the webpage including title and text.

        Returns:
            str: Formatted string containing the webpage title and content
        """
        return f"Webpage Title:\n{self.title}\n\nWebpage Contents:\n{self.text}\n"

    def get_links(self):
        """
        Get all normalized hyperlinks found on the webpage.

        Returns:
            list: List of absolute URLs found on the page
        """
        return self.links

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")

    # test_url = "https://www.superdeporte.es/valencia-cf/2025/08/22/hugo-guillamon-muy-cerca-emigrar-croacia-120860302.html"
    # test_url = "https://plazadeportiva.valenciaplaza.com/plazadeportiva/valenciacf/corberan-rp-previa-osasuna"
    # test_url = "https://www.marca.com/futbol/liga-francesa/2025/08/23/cuenta-atras-ansu-fati.html"
    test_url = "https://www.futbolfantasy.com/laliga/posibles-alineaciones"
    print(f"Fetching: {test_url}")

    w = Website(test_url, timeout=15)

    print("\n=== BASIC PAGE INFO ===")
    print(f"Title: {w.title}")
    print(f"Published at: {w.published_at}")
    print(f"Links found: {len(w.links)}")
    print(f"First 20 links: {w.links[:2000]}")

    print("\n=== ARTICLE TEXT (first 800 chars) ===")
    atxt = (w.text or "").strip()
    print(atxt[:800] + ("..." if len(atxt) > 800 else ""))

    # If you want the full payload:
    # import pprint; pprint.pprint(w.get_article())