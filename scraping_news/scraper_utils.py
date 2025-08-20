import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

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
            # Remove unwanted elements that don't contain useful text
            for tag in soup.body(["script", "style", "img", "input"]):
                tag.decompose()
            # Get all text with newline separators and strip whitespace
            self.text = soup.body.get_text(separator="\n", strip=True)
        else:
            self.text = ""

        # Find all anchor tags with href attributes and normalize the links
        raw_links = soup.find_all("a", href=True)
        self.links = self._normalize_links([a.get("href") for a in raw_links])

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