import streamlit as st
import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, urljoin
import gzip
import io
import time
from collections import deque

# --- Page Config ---
st.set_page_config(page_title="Deep Sitemap Extractor", page_icon="🕸️", layout="wide")

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

def is_sitemap_url(url):
    """
    Heuristic to determine if a URL found in a <url> tag 
    is actually another sitemap.
    """
    u = url.lower()
    return u.endswith('.xml') or u.endswith('.xml.gz') or 'sitemap' in u

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
                return None # Failed to unzip

        # Parse XML
        return ET.fromstring(content)
    except Exception:
        return None

def crawler(start_sitemaps):
    """
    Iterative crawler using a Queue to handle deep nesting without recursion limits.
    """
    queue = deque(start_sitemaps)
    visited_sitemaps = set()
    collected_domains = set()
    
    # Progress UI containers
    status_text = st.empty()
    bar = st.progress(0)
    
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
            # Strip namespace (e.g. {http://www.sitemaps.org/schemas/sitemap/0.9})
            tag = child.tag.split('}')[-1]
            
            # Extract the <loc> text
            loc = None
            for sub in child:
                if sub.tag.split('}')[-1] == 'loc':
                    loc = sub.text.strip() if sub.text else None
                    break
            
            if not loc:
                continue

            # LOGIC 1: Standard Sitemap Index (<sitemap>)
            if tag == 'sitemap':
                if loc not in visited_sitemaps:
                    queue.append(loc)
            
            # LOGIC 2: Standard URL (<url>), BUT we check if it's a hidden sitemap
            elif tag == 'url':
                # Check your specific case: <loc>.../sitemap.xml</loc> inside a <url> tag
                if is_sitemap_url(loc):
                    if loc not in visited_sitemaps:
                        queue.append(loc)
                else:
                    # It's a real page, extract domain
                    try:
                        domain = urlparse(loc).netloc
                        if domain:
                            collected_domains.add(domain)
                    except:
                        pass
        
        processed_count += 1
        # Update progress roughly (visual only)
        if processed_count % 5 == 0:
            pass 

    bar.empty()
    status_text.empty()
    return sorted(list(collected_domains))

# --- UI ---

st.title("🕸️ Deep Recursive Subdomain Extractor")
st.info("Designed for complex sitemap structures where sitemaps are nested inside `<url>` tags.")

url_input = st.text_input("Enter Domain URL:", "https://wiswindows.com/")
start = st.button("Start Extraction", type="primary")

if start and url_input:
    if not url_input.startswith("http"):
        url_input = "https://" + url_input

    with st.spinner("Checking robots.txt..."):
        # 1. Get Initial Sitemaps
        initial_sitemaps = get_sitemap_from_robots(url_input)
        
        if not initial_sitemaps:
            # Fallback
            fallback = urljoin(url_input, "sitemap.xml")
            st.warning(f"No sitemap in robots.txt. Trying {fallback}")
            initial_sitemaps = [fallback]
        else:
            st.success(f"Found entry point: {initial_sitemaps[0]}")

    # 2. Crawl
    results = crawler(initial_sitemaps)

    # 3. Output
    if results:
        st.success(f"Extraction Complete! Found {len(results)} unique subdomains.")
        
        results_string = "\n".join(results)
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.text_area("Extracted Subdomains", results_string, height=400)
        with col2:
            st.download_button(
                "Download .txt",
                results_string,
                file_name="subdomains.txt",
                mime="text/plain"
            )
    else:
        st.error("No subdomains found. The sitemaps might be empty or blocked.")
