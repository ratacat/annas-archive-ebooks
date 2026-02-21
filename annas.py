#!/usr/bin/env python3
"""
Anna's Archive ebook search and download tool.

Requires ANNAS_ARCHIVE_KEY environment variable for downloads.
Get a key by becoming a member at https://annas-archive.li/donate
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.parse
from pathlib import Path


# Mirror domains in order of preference (.org is defunct)
MIRROR_DOMAINS = [
    "annas-archive.gl",
    "annas-archive.li",
    "annas-archive.in",
    "annas-archive.pm",
]

# Status page to discover new mirrors if all known ones fail
MIRROR_DISCOVERY_URL = "https://open-slum.pages.dev/"

# Cache for working domain (set after first successful request)
_working_domain = None


def _discover_mirrors():
    """Scrape open-slum status page for annas-archive domains we don't already know."""
    try:
        req = urllib.request.Request(MIRROR_DISCOVERY_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')
        # Keys look like "annas_archive_li", "annas_archive_pm", etc.
        found = re.findall(r'annas_archive_(\w+)', html)
        # Deduplicate while preserving order, skip "software" prefixed ones
        seen = set()
        domains = []
        for tld in found:
            if tld in seen or tld == 'software':
                continue
            seen.add(tld)
            domain = f"annas-archive.{tld}"
            if domain not in MIRROR_DOMAINS:
                domains.append(domain)
        return domains
    except Exception:
        return []


def get_base_url():
    """Get a working base URL, trying mirrors if needed."""
    global _working_domain

    if _working_domain:
        return f"https://{_working_domain}"

    def _try_domain(domain):
        url = f"https://{domain}/"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    return True
        except Exception:
            pass
        return False

    # Try known mirrors first
    for domain in MIRROR_DOMAINS:
        if _try_domain(domain):
            _working_domain = domain
            print(f"Using mirror: {domain}", file=sys.stderr)
            return f"https://{domain}"

    # All known mirrors failed — check status page for new ones
    print("Known mirrors unreachable, checking for new mirrors...", file=sys.stderr)
    for domain in _discover_mirrors():
        if _try_domain(domain):
            _working_domain = domain
            print(f"Discovered new mirror: {domain}", file=sys.stderr)
            return f"https://{domain}"

    print("Warning: Could not connect to any mirror", file=sys.stderr)
    return f"https://{MIRROR_DOMAINS[0]}"


def get_api_key():
    """Get API key from environment, with helpful error if missing."""
    key = os.environ.get('ANNAS_ARCHIVE_KEY')
    if not key:
        return None
    return key


def _print_membership_message(reason="Membership required", md5=None):
    """Print a friendly message about supporting Anna's Archive."""
    base_url = f"https://{_working_domain}" if _working_domain else f"https://{MIRROR_DOMAINS[0]}"
    manual_section = ""
    if md5:
        manual_section = f"""║                                                                  ║
║  You can still download this book manually in your browser:      ║
║  {base_url + '/md5/' + md5:<63}║
║  (Free slow downloads are available but require a captcha,       ║
║  so they can't be automated.)                                    ║
║                                                                  ║
╠══════════════════════════════════════════════════════════════════╣
"""
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║  {reason:<63}║
╠══════════════════════════════════════════════════════════════════╣
{manual_section}║                                                                  ║
║  Anna's Archive operates as a non-profit, open-source,           ║
║  open-data project. By donating and becoming a member, you       ║
║  support their operations and continued development.             ║
║                                                                  ║
║  Thanks for keeping them going!                                  ║
║                                                                  ║
║  A membership unlocks automated fast downloads and starts        ║
║  at just $2:                                                     ║
║  https://annas-archive.gl/donate?r=7XfHurr                      ║
║                                                                  ║
║  After donating, set your key:                                   ║
║     export ANNAS_ARCHIVE_KEY="your-key-here"                     ║
║                                                                  ║
║  Add to ~/.bashrc or ~/.zshrc to persist across sessions.        ║
╚══════════════════════════════════════════════════════════════════╝
""", file=sys.stderr)


def fetch_url(url, headers=None):
    """Fetch URL and return response text."""
    default_headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    if headers:
        default_headers.update(headers)
    req = urllib.request.Request(url, headers=default_headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        # Read error body — API returns JSON with error details on 403
        try:
            body = e.read().decode('utf-8')
            if body and (body.strip().startswith('{') or body.strip().startswith('[')):
                return body
        except Exception:
            pass
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        return None
    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}", file=sys.stderr)
        return None


def search_books(query, format_filter=None, sort_by_year=True, limit=10, verify=None):
    """
    Search Anna's Archive for books.

    Args:
        query: Search query (title, author, or both)
        format_filter: Optional format filter (pdf, epub, mobi, azw3, djvu)
        sort_by_year: Sort by year descending (most recent first)
        limit: Maximum results to return
        verify: Optional expected title to verify match

    Returns:
        List of book results with md5, title, author, year, format
    """
    params = {'q': query}
    if format_filter:
        params['ext'] = format_filter
    if sort_by_year:
        params['sort'] = 'year_desc'

    base_url = get_base_url()
    url = f"{base_url}/search?{urllib.parse.urlencode(params)}"
    html = fetch_url(url)

    if not html:
        return []

    # Parse results from HTML
    results = []

    # Find all MD5 hashes
    md5s = list(dict.fromkeys(re.findall(r'/md5/([a-f0-9]{32})', html)))

    for md5 in md5s[:limit]:
        # Find context around this MD5
        idx = html.find(f'href="/md5/{md5}"')
        if idx == -1:
            continue

        # Get chunk around result
        start = max(0, html.rfind('<div class="flex', 0, idx))
        end = html.find('<div class="flex', idx + 100)
        if end == -1:
            end = idx + 3000
        chunk = html[start:end]

        # Extract metadata
        title_match = re.search(r'js-vim-focus[^>]*>([^<]+)</a>', chunk)
        author_match = re.search(r'mdi--user-edit[^>]*></span>\s*([^<]+)</a>', chunk)
        publisher_match = re.search(r'mdi--company[^>]*></span>\s*([^<]+)</a>', chunk)
        filepath_match = re.search(r'text-gray-500 font-mono">([^<]+)</div>', chunk)

        title = title_match.group(1).strip() if title_match else None
        author = author_match.group(1).strip() if author_match else None
        pub_year = publisher_match.group(1).strip() if publisher_match else None
        filepath = filepath_match.group(1).strip() if filepath_match else None

        # Extract year from publisher string
        year = None
        if pub_year:
            year_match = re.search(r'\b(19|20)\d{2}\b', pub_year)
            if year_match:
                year = year_match.group(0)

        # Extract extension from filepath
        extension = None
        if filepath:
            ext_match = re.search(r'\.(\w+)$', filepath)
            if ext_match:
                extension = ext_match.group(1).lower()

        if title:  # Only add if we found a title
            results.append({
                'md5': md5,
                'title': title,
                'author': author,
                'year': year,
                'publisher': pub_year,
                'format': extension,
                'filepath': filepath
            })

    # If verify is set, check for title match
    if verify and results:
        verify_lower = verify.lower()
        for r in results:
            if verify_lower in r['title'].lower():
                r['verified'] = True

    return results


def get_book_details(md5):
    """
    Get detailed information about a book.

    Args:
        md5: Book MD5 hash

    Returns:
        Dictionary with book details
    """
    base_url = get_base_url()
    url = f"{base_url}/md5/{md5}"
    html = fetch_url(url)

    if not html:
        return None

    details = {'md5': md5}

    # Extract title and author from data-content attributes
    title_match = re.search(r'data-content="([^"]+)"[^>]*></div>\s*<div[^>]*data-content="([^"]+)"', html)
    if title_match:
        details['title'] = title_match.group(1)
        details['author'] = title_match.group(2)

    # Extract from page title as fallback
    if 'title' not in details:
        page_title = re.search(r'<title>([^<]+)', html)
        if page_title:
            details['title'] = page_title.group(1).replace(" - Anna's Archive", "").strip()

    # Find download options
    fast_downloads = re.findall(r'href="/fast_download/([^/]+)/(\d+)/(\d+)"', html)
    slow_downloads = re.findall(r'href="/slow_download/([^/]+)/(\d+)/(\d+)"', html)

    details['download_options'] = {
        'fast': [{'md5': d[0], 'path_index': d[1], 'domain_index': d[2]} for d in fast_downloads[:4]],
        'slow': [{'md5': d[0], 'path_index': d[1], 'domain_index': d[2]} for d in slow_downloads[:4]]
    }

    # Extract additional metadata from the page
    # File size, language, year, etc. are in various places

    return details


def download_book(md5, output_dir=None, path_index=0, domain_index=0):
    """
    Download a book using the fast download API.

    Args:
        md5: Book MD5 hash
        output_dir: Directory to save file (default: current directory)
        path_index: Collection index (default: 0)
        domain_index: Server index (default: 0)

    Returns:
        Path to downloaded file or None on failure
    """
    key = get_api_key()
    if not key:
        _print_membership_message("ANNAS_ARCHIVE_KEY not set", md5=md5)
        return None


    # Call fast download API
    params = {
        'md5': md5,
        'key': key,
        'path_index': path_index,
        'domain_index': domain_index
    }

    base_url = get_base_url()
    api_url = f"{base_url}/dyn/api/fast_download.json?{urllib.parse.urlencode(params)}"

    response = fetch_url(api_url)
    if not response:
        return None

    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        print(f"Invalid JSON response: {response[:200]}", file=sys.stderr)
        return None

    if data.get('error'):
        error_msg = data['error']
        if 'not a member' in error_msg.lower() or 'invalid' in error_msg.lower() or 'expired' in error_msg.lower():
            _print_membership_message(error_msg, md5=md5)
        else:
            print(f"API Error: {error_msg}", file=sys.stderr)
        return None

    download_url = data.get('download_url')
    if not download_url:
        print("No download URL in response", file=sys.stderr)
        return None

    # Download the file
    output_dir = Path(output_dir) if output_dir else Path.cwd()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get filename from URL or use MD5
    filename = download_url.split('/')[-1].split('?')[0]
    # URL-decode the filename
    filename = urllib.parse.unquote(filename)
    # Sanitize: remove problematic characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)

    if not filename or filename == md5:
        # Try to get details for better filename
        details = get_book_details(md5)
        if details and details.get('title'):
            # Sanitize title for filename
            safe_title = re.sub(r'[^\w\s-]', '', details['title'])[:50]
            filename = f"{safe_title}.pdf"  # Assume PDF, will be corrected by content-type
        else:
            filename = f"{md5}.pdf"

    output_path = output_dir / filename

    print(f"Downloading to: {output_path}")

    try:
        urllib.request.urlretrieve(download_url, output_path)
        print(f"Downloaded: {output_path}")
        return str(output_path)
    except Exception as e:
        print(f"Download failed: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Search and download ebooks from Anna's Archive",
        epilog="Requires ANNAS_ARCHIVE_KEY environment variable for downloads."
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search for books')
    search_parser.add_argument('query', help='Search query (title, author, or both)')
    search_parser.add_argument('--format', '-f', choices=['pdf', 'epub', 'mobi', 'azw3', 'djvu'],
                               help='Filter by format')
    search_parser.add_argument('--limit', '-l', type=int, default=10,
                               help='Maximum results (default: 10)')
    search_parser.add_argument('--verify', '-v', help='Verify title contains this string')
    search_parser.add_argument('--json', '-j', action='store_true', help='Output as JSON')

    # Details command
    details_parser = subparsers.add_parser('details', help='Get book details')
    details_parser.add_argument('md5', help='Book MD5 hash')
    details_parser.add_argument('--json', '-j', action='store_true', help='Output as JSON')

    # Download command
    download_parser = subparsers.add_parser('download', help='Download a book')
    download_parser.add_argument('md5', help='Book MD5 hash')
    download_parser.add_argument('--output', '-o', help='Output directory')
    download_parser.add_argument('--path-index', type=int, default=0,
                                 help='Collection index (default: 0)')
    download_parser.add_argument('--domain-index', type=int, default=0,
                                 help='Server index (default: 0)')

    # Check key command
    check_parser = subparsers.add_parser('check-key', help='Check if API key is set')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == 'check-key':
        key = get_api_key()
        if key:
            print(f"Key is set: {key[:8]}...{key[-4:]}")
        return

    if args.command == 'search':
        results = search_books(
            args.query,
            format_filter=args.format,
            limit=args.limit,
            verify=args.verify
        )

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            if not results:
                print("No results found")
                return

            for i, r in enumerate(results, 1):
                verified = " [VERIFIED]" if r.get('verified') else ""
                print(f"\n{i}. {r['title']}{verified}")
                print(f"   Author: {r['author'] or 'Unknown'}")
                print(f"   Year: {r['year'] or 'Unknown'} | Format: {r['format'] or 'Unknown'}")
                print(f"   MD5: {r['md5']}")

    elif args.command == 'details':
        details = get_book_details(args.md5)

        if args.json:
            print(json.dumps(details, indent=2))
        else:
            if not details:
                print("Book not found")
                return

            print(f"\nTitle: {details.get('title', 'Unknown')}")
            print(f"Author: {details.get('author', 'Unknown')}")
            print(f"MD5: {details['md5']}")

            if details.get('download_options'):
                fast = details['download_options'].get('fast', [])
                slow = details['download_options'].get('slow', [])
                print(f"\nDownload options: {len(fast)} fast, {len(slow)} slow")

    elif args.command == 'download':
        result = download_book(
            args.md5,
            output_dir=args.output,
            path_index=args.path_index,
            domain_index=args.domain_index
        )

        if result:
            print(f"\nSuccess! File saved to: {result}")
        else:
            print("\nDownload failed", file=sys.stderr)
            sys.exit(1)


if __name__ == '__main__':
    main()
