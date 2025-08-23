from unittest.mock import patch, Mock
from scraping_news.scraper_utils import Website

def _mk_response(html: str, content_type: str = "text/html"):
    """Small helper to build a mocked HTTP response."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": content_type}
    mock_response.content = html.encode("utf-8")
    return mock_response

# Simulate a valid HTML page with <a> tags
@patch("scraping_news.scraper_utils.requests.get")
def test_get_links_returns_expected_links(mock_get):
    """
    Test that Website.get_links() extracts valid URLs from HTML content.

    Mocks HTTP response with HTML containing relative, absolute, and javascript links.
    Verifies that relative URLs are converted to absolute and javascript links are filtered out.

    Expected: Returns list with absolute URLs only, excluding non-HTTP schemes.
    """
    html = """
    <html><body>
        <a href="/link1">Link 1</a>
        <a href="https://example.com/link2">Link 2</a>
        <a href="javascript:void(0)">Skip me</a>
    </body></html>
    """

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.content = html.encode("utf-8")

    mock_get.return_value = mock_response

    website = Website("https://example.com")
    links = website.get_links()

    assert isinstance(links, list)
    assert "https://example.com/link1" in links
    assert "https://example.com/link2" in links
    assert not any("javascript" in l for l in links)

# Simulate a valid page with no links
@patch("scraping_news.scraper_utils.requests.get")
def test_get_links_returns_empty_on_no_anchors(mock_get):
    html = "<html><body><p>No links here</p></body></html>"

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.headers = {"Content-Type": "text/html"}
    mock_response.content = html.encode("utf-8")

    mock_get.return_value = mock_response

    website = Website("https://example.com")
    links = website.get_links()

    assert links == []

# A1. Basic <article> success
@patch("scraping_news.scraper_utils.requests.get")
def test_article_text_basic_article_container(mock_get):
    """
    Should extract text only from <article> including h1–h4, p, and li, in DOM order.
    """
    html = """
    <html><head><title>Sample</title></head><body>
      <article>
        <h1>Headline</h1>
        <p>First paragraph.</p>
        <h2>Subheading</h2>
        <p>Second paragraph.</p>
        <ul><li>Point A</li><li>Point B</li></ul>
      </article>
    </body></html>
    """
    mock_get.return_value = _mk_response(html)
    w = Website("https://example.com")
    # Expect DOM-ordered join with \n\n separators (from clean_and_join)
    expected = "Headline\n\nFirst paragraph.\n\nSubheading\n\nSecond paragraph.\n\nPoint A\n\nPoint B"
    assert w.text == expected


# A2. Common CMS selector success (no <article>)
@patch("scraping_news.scraper_utils.requests.get")
def test_article_text_common_cms_selector(mock_get):
    """
    When no <article> exists, should use known containers like .entry-content.
    """
    html = """
    <html><body>
      <div class="entry-content">
        <h1>CMS Headline</h1>
        <p>Body paragraph.</p>
        <h3>Details</h3>
        <ul><li>Bullet 1</li><li>Bullet 2</li></ul>
      </div>
      <div class="sidebar">Ignore me</div>
    </body></html>
    """
    mock_get.return_value = _mk_response(html)
    w = Website("https://example.com")
    expected = "CMS Headline\n\nBody paragraph.\n\nDetails\n\nBullet 1\n\nBullet 2"
    assert w.text == expected
    # Ensure sidebar didn't leak
    assert "Ignore me" not in w.text


# A3. Junk removal inside the article
@patch("scraping_news.scraper_utils.requests.get")
def test_article_text_junk_removed_inside_article(mock_get):
    """
    Junk elements (script/style/aside/figure/figcaption/nav/header/footer/img/input)
    inside the article should be removed from the extracted text.
    """
    html = """
    <html><body>
      <article>
        <header>Top chrome</header>
        <h1>Clean Headline</h1>
        <script>var x=1;</script>
        <p>Important text.</p>
        <aside>Related promo</aside>
        <figure><img src="x.jpg"><figcaption>Caption</figcaption></figure>
        <footer>Footer stuff</footer>
        <p>More content here.</p>
      </article>
    </body></html>
    """
    mock_get.return_value = _mk_response(html)
    w = Website("https://example.com")
    expected = "Clean Headline\n\nImportant text.\n\nMore content here."
    assert w.text == expected
    # Ensure junk is gone
    for junk in ["Top chrome", "Related promo", "Caption", "Footer stuff"]:
        assert junk not in w.text


# A4. Menu noise is ignored (large nav/header before article)
@patch("scraping_news.scraper_utils.requests.get")
def test_article_text_ignores_menu_noise(mock_get):
    """
    Large header/nav menus should not appear in the final text; only article content should.
    """
    html = """
    <html><body>
      <nav>
        <a>Inicio</a><a>En directo</a><a>Galerías</a><a>Fútbol</a>
      </nav>
      <header>Global Site Header</header>
      <article>
        <h1>Real Headline</h1>
        <p>Real paragraph 1.</p>
        <p>Real paragraph 2.</p>
      </article>
      <footer>Global Site Footer</footer>
    </body></html>
    """
    mock_get.return_value = _mk_response(html)
    w = Website("https://example.com")
    expected = "Real Headline\n\nReal paragraph 1.\n\nReal paragraph 2."
    assert w.text == expected
    # Assert menu strings are absent
    for menu in ["Inicio", "En directo", "Galerías", "Fútbol", "Global Site Header", "Global Site Footer"]:
        assert menu not in w.text


# A5. Fallback to the container with the most <p> text
@patch("scraping_news.scraper_utils.requests.get")
def test_article_text_fallback_longest_p_cluster(mock_get):
    """
    If no <article> or known container is present, choose the div/section/main
    that contains the largest total <p> text.
    """
    html = """
    <html><body>
      <div id="menu"><p>Small</p></div>
      <section id="short-blurb"><p>Short.</p></section>
      <main id="body">
        <div><p>First long paragraph about the topic.</p></div>
        <div><p>Second long paragraph continues the discussion.</p></div>
      </main>
    </body></html>
    """
    mock_get.return_value = _mk_response(html)
    w = Website("https://example.com")
    expected = "First long paragraph about the topic.\n\nSecond long paragraph continues the discussion."
    assert w.text == expected
    assert "Small" not in w.text
    assert "Short." not in w.text


# A6. Headings & lists included, order preserved
@patch("scraping_news.scraper_utils.requests.get")
def test_article_text_headings_and_lists_included(mock_get):
    """
    Headings (h1–h4) and list items should be included and appear in DOM order,
    separated by double newlines as implemented.
    """
    html = """
    <html><body>
      <article>
        <h1>Title</h1>
        <p>Intro paragraph.</p>
        <h3>Key Points</h3>
        <ul><li>One</li><li>Two</li></ul>
        <h4>Details</h4>
        <p>Closing.</p>
      </article>
    </body></html>
    """
    mock_get.return_value = _mk_response(html)
    w = Website("https://example.com")
    expected = "Title\n\nIntro paragraph.\n\nKey Points\n\nOne\n\nTwo\n\nDetails\n\nClosing."
    assert w.text == expected

    # Simple order checks (indexes must increase)
    idx_title = w.text.index("Title")
    idx_intro = w.text.index("Intro paragraph.")
    idx_key   = w.text.index("Key Points")
    idx_one   = w.text.index("One")
    idx_two   = w.text.index("Two")
    idx_det   = w.text.index("Details")
    idx_close = w.text.index("Closing.")
    assert idx_title < idx_intro < idx_key < idx_one < idx_two < idx_det < idx_close


# A7. Empty/degenerate cases
@patch("scraping_news.scraper_utils.requests.get")
def test_article_text_empty_or_no_valid_content(mock_get):
    """
    If no valid article container and no <p>/headings/list items exist, text should be empty.
    """
    html = """
    <html><body>
      <div class="layout">
        <figure><img src="x.jpg"><figcaption>Ignore caption</figcaption></figure>
        <aside>Sidebar only</aside>
        <nav><a>Menu</a></nav>
      </div>
    </body></html>
    """
    mock_get.return_value = _mk_response(html)
    w = Website("https://example.com")
    assert w.text == ""