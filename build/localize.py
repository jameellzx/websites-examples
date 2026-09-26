"""Snapshot a server-rendered page (e.g. an EComposer demo preview) into a
self-contained folder: downloads images/CSS/JS (and assets referenced from CSS)
into <out>/assets/ and rewrites references. Google Fonts links stay remote.

usage: python localize.py <source.html> <page-url> <out-dir>
"""
import hashlib, os, re, sys, urllib.parse, urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"
KEEP_REMOTE = ("fonts.googleapis.com", "fonts.gstatic.com", "www.w3.org")
DROP = ("cloudflareinsights.com",)
URL_RE = re.compile(r"""(?:https?:)?//[^\s"'()<>,\\]+""")

src, base, out = sys.argv[1:4]
assets = os.path.join(out, "assets")
os.makedirs(assets, exist_ok=True)
cache = {}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": base})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def local_name(url):
    p = urllib.parse.urlparse(url)
    name = os.path.basename(p.path) or "file"
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)[-60:]
    stem, ext = os.path.splitext(name)
    h = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{stem}-{h}{ext}"


def localize(url, prefix):
    """Download url, return path relative to the referencing file (prefix)."""
    full = "https:" + url if url.startswith("//") else url
    host = urllib.parse.urlparse(full).netloc
    if any(k in host for k in KEEP_REMOTE):
        return url
    if full in cache:
        return prefix + cache[full]
    name = local_name(full)
    cache[full] = name
    try:
        data = fetch(full)
    except Exception as e:
        print("FAIL", full, e)
        cache[full] = None
        return url
    if name.endswith(".css"):
        text = data.decode("utf-8", "replace")
        text = rewrite_css(text, full, "")
        data = text.encode()
    with open(os.path.join(assets, name), "wb") as f:
        f.write(data)
    print("ok", name, len(data))
    return prefix + name


def rewrite_css(text, css_url, prefix):
    def rep(m):
        raw = m.group(2).strip()
        if raw.startswith("data:") or raw.startswith("#"):
            return m.group(0)
        absu = urllib.parse.urljoin(css_url, raw)
        return f"url({m.group(1)}{localize(absu, prefix)}{m.group(1)})"
    return re.sub(r"""url\((['"]?)([^'")]+)\1\)""", rep, text)


html = open(src, encoding="utf-8").read()

# drop analytics
html = re.sub(r"<script[^>]*(?:%s)[^>]*>\s*</script>" % "|".join(DROP), "", html)
html = re.sub(r"<script[^>]*>[^<]*(?:%s)[^<]*</script>" % "|".join(DROP), "", html)


def is_asset(u):
    path = urllib.parse.urlparse("https:" + u if u.startswith("//") else u).path.lower()
    return bool(re.search(r"\.(css|js|png|jpe?g|gif|webp|avif|svg|mp4|webm|woff2?|ttf|otf|ico)$", path))


def rep_url(m):
    u = m.group(0).rstrip(".")
    tail = m.group(0)[len(u):]
    host = urllib.parse.urlparse("https:" + u if u.startswith("//") else u).netloc
    if any(k in host for k in KEEP_REMOTE) or not is_asset(u):
        return m.group(0)
    return localize(u, "assets/") + tail

# unescape JSON-escaped slashes so URLs inside data attributes are found too
html = html.replace("\\/", "/")
html = URL_RE.sub(rep_url, html)
# root-relative assets (/css/.., /js/..) served by the demo host
html = re.sub(r"""(src|href)=(["'])(/[^/"'][^"']*)\2""",
              lambda m: f'{m.group(1)}={m.group(2)}{localize(urllib.parse.urljoin(base, m.group(3)), "assets/") if is_asset(m.group(3)) else m.group(3)}{m.group(2)}',
              html)

with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
    f.write(html)
print("done", len(cache), "assets")
