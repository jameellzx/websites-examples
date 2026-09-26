"""Render a cloned Shopify theme's ck-* template into a plain static HTML page.

Runs fully offline: reads the theme's Liquid files from disk and renders them with
python-liquid plus small stand-ins for Shopify-only filters and objects.

Usage: python render.py <theme_dir> <template.json> <out_dir> [products.json]
"""
import json
import re
import shutil
import sys
from pathlib import Path

from liquid import Environment
from liquid import DictLoader
from liquid.builtin.expressions import logical as _logical
from liquid.exceptions import LiquidTypeError

# Shopify treats `nil > nil` as false instead of raising; match that.
_strict_lt = _logical._lt


def _lenient_lt(*args, **kwargs):
    try:
        return _strict_lt(*args, **kwargs)
    except LiquidTypeError:
        return False


_logical._lt = _lenient_lt

# Shopify treats nil / undefined as `blank`; python-liquid does not.
_strict_eq = _logical._eq


def _blank_aware_eq(left, right):
    from liquid.builtin.expressions.primitive import Blank
    from liquid.undefined import Undefined
    for a, b in ((left, right), (right, left)):
        if isinstance(a, Blank) and (b is None or isinstance(b, Undefined)):
            return True
    return _strict_eq(left, right)


_logical._eq = _blank_aware_eq

theme = Path(sys.argv[1])
template = theme / "templates" / sys.argv[2]
out = Path(sys.argv[3])
products_file = Path(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4] else None


def load_json(path):
    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r"^\s*/\*.*?\*/", "", raw, flags=re.S)
    return json.loads(raw)


# ---- fonts --------------------------------------------------------------
GOOGLE_FONTS = set()


class Font(dict):
    """Stand-in for a Shopify font_picker value such as 'libre_baskerville_n7'."""

    def __init__(self, handle):
        name, _, variant = handle.rpartition("_")
        family = " ".join(w.capitalize() for w in name.split("_"))
        weight = int(variant[1:]) * 100 if variant[1:].isdigit() else 400
        style = "italic" if variant.startswith("i") else "normal"
        GOOGLE_FONTS.add(family)
        super().__init__(
            family=f'"{family}"',
            fallback_families="sans-serif" if "baskerville" not in name else "serif",
            weight=weight,
            style=style,
            system=False,
        )

    def __str__(self):
        return self["family"]


def to_value(setting_type, value):
    if setting_type == "font_picker" and isinstance(value, str) and value:
        return Font(value)
    if setting_type in ("image_picker", "video", "collection", "product", "url_or_blank"):
        return value if value else None
    return value


def schema_of(source):
    m = re.search(r"{%-?\s*schema\s*-?%}(.*?){%-?\s*endschema\s*-?%}", source, re.S)
    return json.loads(m.group(1)) if m else {}


def merged_settings(schema_settings, values):
    result = {}
    for s in schema_settings:
        if "id" not in s:
            continue
        v = values.get(s["id"], s.get("default"))
        result[s["id"]] = to_value(s.get("type"), v)
    for k, v in values.items():
        result.setdefault(k, v)
    return result


# ---- products (only needed when a section lists products) -----------------
class Product(dict):
    def __init__(self, d):
        price = int(d["price"])
        compare = int(d.get("compare_at_price") or 0) or None
        variant = {"id": 1, "price": price, "compare_at_price": compare, "available": True,
                   "title": "Default Title", "options": []}
        img = d.get("image")
        super().__init__(
            title=d["title"], vendor=d.get("vendor", ""), url="#", handle="p",
            available=True, price=price, price_min=price, price_varies=False,
            compare_at_price=compare, has_only_default_variant=True,
            featured_media={"alt": d["title"], "src": img, "preview_image": {"src": img}} if img else None,
            selected_or_first_available_variant=variant, variants=[variant],
            first_available_variant=variant,
        )


PRODUCTS = []
if products_file:
    PRODUCTS = [Product(p) for p in json.loads(products_file.read_text(encoding="utf-8"))]


# ---- filters ------------------------------------------------------------
def image_url(img, **kw):
    if isinstance(img, dict):
        return img.get("src") or ""
    return img or ""


def image_tag(url, **kw):
    attrs = " ".join(f'{k}="{v}"' for k, v in kw.items() if k in ("class", "alt", "loading", "sizes") and v is not None)
    return f'<img src="{url}" {attrs}>'


def money(cents):
    try:
        return f"${int(cents) / 100:,.2f}"
    except (TypeError, ValueError):
        return ""


def asset_url(name):
    return f"assets/{name}"


env = Environment()
env.filters.update({
    "image_url": image_url,
    "image_tag": image_tag,
    "img_url": image_url,
    "money": money,
    "money_with_currency": money,
    "money_without_trailing_zeros": lambda c: money(c).replace(".00", ""),
    "asset_url": asset_url,
    "font_face": lambda f, **kw: "",
    "font_modify": lambda f, *a: f,
    "font_url": lambda f: "",
    "stylesheet_tag": lambda u, **kw: f'<link rel="stylesheet" href="{u}">',
    "script_tag": lambda u: f'<script src="{u}"></script>',
    "t": lambda key, **kw: key.split(".")[-1].replace("_", " ").capitalize(),
    "default_errors": lambda e: "",
    "payment_type_svg_tag": lambda t, **kw: "",
    "video_tag": lambda v, **kw: "",
    "handle": lambda s: re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-"),
    "handleize": lambda s: re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-"),
    "json": lambda v: json.dumps(v),
    "color_to_rgb": lambda c: c,
    "within": lambda u, c: u,
})

STYLES, SCRIPTS = [], []


def preprocess(src):
    """Turn Shopify-only tags into plain HTML / collect section CSS and JS."""
    src = re.sub(r"{%-?\s*schema\s*-?%}.*?{%-?\s*endschema\s*-?%}", "", src, flags=re.S)

    def grab(bucket):
        def f(m):
            bucket.append(m.group(1))
            return ""
        return f

    src = re.sub(r"{%-?\s*stylesheet\s*-?%}(.*?){%-?\s*endstylesheet\s*-?%}", grab(STYLES), src, flags=re.S)
    src = re.sub(r"{%-?\s*javascript\s*-?%}(.*?){%-?\s*endjavascript\s*-?%}", grab(SCRIPTS), src, flags=re.S)
    src = re.sub(r"{%-?\s*style\s*-?%}", "<style>", src)
    src = re.sub(r"{%-?\s*endstyle\s*-?%}", "</style>", src)
    src = re.sub(r"{%-?\s*form\b[^%]*-?%}", '<form onsubmit="return false">', src)
    src = re.sub(r"{%-?\s*endform\s*-?%}", "</form>", src)
    # form tag leaves `form.*` references behind; neutralise the common ones
    return src


snippets = {}
for f in (theme / "snippets").glob("*.liquid"):
    snippets[f.stem] = preprocess(f.read_text(encoding="utf-8"))
env.loader = DictLoader(snippets)

settings_values = {}
schema_path = theme / "config" / "settings_schema.json"
if schema_path.exists():
    for group in load_json(schema_path):
        for s in group.get("settings", []):
            if "id" in s:
                settings_values[s["id"]] = to_value(s.get("type"), s.get("default"))
data = load_json(theme / "config" / "settings_data.json")
current = data["current"]
current = data.get("presets", {}).get(current, {}) if isinstance(current, str) else current
for k, v in current.items():
    if k not in ("sections", "content_for_index", "blocks", "color_schemes"):
        settings_values[k] = v

globals_ = {
    "settings": settings_values,
    "request": {"design_mode": False, "page_type": "index", "locale": {"iso_code": "en"}},
    "routes": {"root_url": "/", "cart_url": "#", "cart_add_url": "#", "all_products_collection_url": "#",
               "search_url": "#", "account_url": "#"},
    "shop": {"name": "", "currency": "USD", "money_format": "${{amount}}"},
    "cart": {"item_count": 0, "items": []},
    "form": {"posted_successfully?": False, "errors": None},
    "product": None,
    "collections": {},
    "localization": {},
}

tpl = load_json(template)
body = []
for key in tpl["order"]:
    sec = tpl["sections"][key]
    if sec.get("disabled"):
        continue
    source = (theme / "sections" / f"{sec['type']}.liquid").read_text(encoding="utf-8")
    schema = schema_of(source)
    ssettings = merged_settings(schema.get("settings", []), sec.get("settings", {}))
    block_schemas = {b["type"]: b for b in schema.get("blocks", [])}
    blocks = []
    for bid in sec.get("block_order", []):
        b = sec["blocks"][bid]
        if b.get("disabled"):
            continue
        bs = block_schemas.get(b["type"], {})
        blocks.append({"id": bid, "type": b["type"], "shopify_attributes": "",
                       "settings": merged_settings(bs.get("settings", []), b.get("settings", {}))})
    if PRODUCTS and ssettings.get("collection") is not None or (PRODUCTS and "collection" in ssettings):
        ssettings["collection"] = {"products": PRODUCTS, "url": "#", "title": "Products"}
    section = {"id": key, "settings": ssettings, "blocks": blocks, "index": len(body) + 1}
    html = env.from_string(preprocess(source)).render(**globals_, section=section)
    body.append(f'<div id="shopify-section-{key}" class="shopify-section">{html}</div>')

# ck-fonts snippet (if the theme has one) declares the self-hosted clone fonts
fonts_html = ""
if "ck-fonts" in snippets:
    fonts_html = env.from_string(snippets["ck-fonts"]).render(**globals_)

families = "&".join("family=" + f.replace(" ", "+") + ":wght@300;400;500;600;700;800;900"
                    for f in sorted(GOOGLE_FONTS))
overrides = '<link rel="stylesheet" href="overrides.css">' if (out / "overrides.css").exists() else ""
title = sys.argv[5] if len(sys.argv) > 5 else "Example site"
page = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="robots" content="noindex">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?{families}&display=swap">
<style>
*,*::before,*::after{{box-sizing:border-box}}
html{{-webkit-text-size-adjust:100%}}
body{{margin:0;font-family:"Lato",system-ui,sans-serif;color:#222;background:#fff}}
img{{max-width:100%;height:auto;display:block}}
a{{color:inherit}}
button{{font:inherit;cursor:pointer}}
.visually-hidden{{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}}
{''.join(STYLES)}
</style>
{fonts_html}
{overrides}
</head><body>
{''.join(body)}
<script>{''.join(SCRIPTS)}</script>
</body></html>
"""
out.mkdir(parents=True, exist_ok=True)
(out / "index.html").write_text(page, encoding="utf-8")

# copy only the theme assets the page actually references
used = set(re.findall(r"assets/([^\"')\s?]+)", page))
(out / "assets").mkdir(exist_ok=True)
for name in used:
    src = theme / "assets" / name
    if src.exists():
        shutil.copy2(src, out / "assets" / name)
print(f"wrote {out/'index.html'} ({len(page)//1024} KB), {len(used)} assets, fonts: {sorted(GOOGLE_FONTS)}")
