import re

def sanitize_html(raw_html: str) -> str:
    """Sanitizes raw HTML to prevent XSS while preserving email layout."""
    if not raw_html:
        return ""
    # Strip script and iframe tags
    clean = re.sub(r'<script.*?>.*?</script>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r'<iframe.*?>.*?</iframe>', '', clean, flags=re.DOTALL | re.IGNORECASE)
    clean = re.sub(r'on\w+=".*?"', '', clean, flags=re.IGNORECASE)
    return clean

def resolve_cid_images(html_content: str) -> str:
    """Replaces cid:image001.png links with inline SVG placeholder icon or data URLs."""
    if not html_content or "cid:" not in html_content:
        return html_content
    # Replace cid images with a clean placeholder graphic
    resolved = re.sub(
        r'src=["\']cid:(.*?)["\']',
        r'src="data:image/svg+xml;utf8,<svg xmlns=\'http://www.w3.org/2000/svg\' width=\'24\' height=\'24\' viewBox=\'0 0 24 24\' fill=\'none\' stroke=\'%236366f1\' stroke-width=\'2\'><rect x=\'3\' y=\'3\' width=\'18\' height=\'18\' rx=\'2\'/><circle cx=\'8.5\' cy=\'8.5\' r=\'1.5\'/><polyline points=\'21 15 16 10 5 21\'/></svg>"',
        html_content,
        flags=re.IGNORECASE
    )
    return resolved
