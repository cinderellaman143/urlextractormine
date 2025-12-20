import streamlit as st
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, urljoin
import gzip
import io
import time
from collections import deque

# --- Page Config ---
st.set_page_config(page_title="Fast Homepage Extractor", page_icon="⚡", layout="wide")

st.markdown("""
<style>
    .stTextArea textarea { font-family: 'Courier New', monospace; font-size: 12px; }
    div[data-testid="stStatusWidget"] { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# --- Logic ---

def get_sitemap_from_robots(domain_url):
    """Finds the initial sitemap from robots.txt"""
    robots_url = urljoin(domain_url, "/robots.txt")
    sitemaps = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; SitemapExtractor/1.0)'}
        response = requests.get(robots_url, headers=headers, timeout=10)
        if response.status_code == 200:
            for line in response.text.splitlines():
                if line.lower().strip().startswith('sitemap:'):
                    sitemaps.append(line.split(':', 1)[1].strip())
    except Exception:
        pass
    return sitemaps

def is_homepage(url):
    """
    Checks if a URL is a root homepage (e.g., https://sub.domain.com/ or https://sub.domain.com)
    and excludes files or deep paths.
    """
    parsed = urlparse(url)
    path = parsed.path
    # True if path is empty or just '/'
    return path in ['', '/']

def fetch_and_parse(url):
    """
    Fetches a URL and returns the XML root element.
    Handles Gzip automatically.
    """
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; SitemapExtractor/1.0)'}
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            return None
        
        content = response.content
        # Handle GZIP
        if url.endswith('.gz') or response.headers.get('Content-Type') == 'application/x-gzip':
            try:
                content = gzip.GzipFile(fileobj=io.BytesIO(content)).read()
            except:
                return None 

        return ET.fromstring(content)
    except Exception:
        return None

def fast_crawler(start_sitemaps):
    """
    Crawler that only follows explicit <sitemap> tags and extracts only Homepage URLs.
    It does NOT recurse into <url> tags (even if they are xml).
    """
    queue = deque(start_sitemaps)
    visited_sitemaps = set()
    collected_domains = set()
    
    status_text = st.empty()
    bar = st.progress(0)
    
    # We use a placeholder for total count to show progress isn't stuck
    count_placeholder = st.empty()
    processed_count = 0
    
    while queue:
        current_url = queue.popleft()
        
        if current_url in visited_sitemaps:
            continue
        visited_sitemaps.add(current_url)
        
        status_text.text(f"Scanning Sitemap: {current_url}")
        
        root = fetch_and_parse(current_url)
        if root is None:
            continue

        # Parse Children
        for child in root:
            # Strip namespace
            tag = child.tag.split('}')[-1]
            
            # Extract <loc>
            loc = None
            for sub in child:
                if sub.tag.split('}')[-1] == 'loc':
                    loc = sub.text.strip() if sub.text else None
                    break
            
            if not loc:
                continue

            # LOGIC 1: Sitemap Index (<sitemap>) -> ALWAYS FOLLOW (These are folders/categories)
            if tag == 'sitemap':
                if loc not in visited_sitemaps:
                    queue.append(loc)
            
            # LOGIC 2: Standard URL (<url>) -> ONLY KEEP HOMEPAGES, DO NOT RECURSE
            elif tag == 'url':
                # Only keep if it is a root homepage
                if is_homepage(loc):
                    # Extract pure domain to ensure uniqueness
                    try:
                        domain = urlparse(loc).netloc
                        if domain:
                            collected_domains.add(domain)
                    except:
                        pass
        
        processed_count += 1
        count_placeholder.caption(f"Sitemaps processed: {processed_count} | Unique Domains found: {len(collected_domains)}")
        
        # Simple progress bar animation
        if processed_count % 10 == 0:
            pass 

    bar.empty()
    status_text.empty()
    return sorted(list(collected_domains))

# --- UI ---

st.title("⚡ Fast Sitemap Homepage Extractor")
st.markdown("""
This tool is optimized for speed. 
1. It follows `Sitemap Indexes`.
2. It **only extracts Homepage URLs** (e.g. `sub.domain.com/`).
3. It ignores deep pages and deep sitemaps to finish quickly.
""")

url_input = st.text_input("Enter Domain URL:", "https://wiswindows.com/")
start = st.button("Start Fast Extraction", type="primary")

if start and url_input:
    if not url_input.startswith("http"):
        url_input = "https://" + url_input

    with st.spinner("Checking robots.txt..."):
        initial_sitemaps = get_sitemap_from_robots(url_input)
        
        if not initial_sitemaps:
            fallback = urljoin(url_input, "sitemap.xml")
            st.warning(f"No sitemap in robots.txt. Trying {fallback}")
            initial_sitemaps = [fallback]
        else:
            st.success(f"Found entry point: {initial_sitemaps[0]}")

    results = fast_crawler(initial_sitemaps)

    if results:
        st.success(f"Done! Found {len(results)} unique domains.")
        
        results_string = "\n".join(results)
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.text_area("Extracted Domains", results_string, height=400)
        with col2:
            st.download_button(
                "Download List",
                results_string,
                file_name="fast_subdomains.txt",
                mime="text/plain"
            )
    else:
        st.error("No subdomains found. The sitemaps might be empty or blocked.")
