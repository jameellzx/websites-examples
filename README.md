# Website examples

Store landing pages rebuilt from reference designs, rendered to plain HTML.

- `petpad/`: Pet Pad Store product landing page
- `glow/`: Glow spa and skincare landing page

The pages were built as Shopify themes. `build/render.py` renders a theme's Liquid template to static HTML offline, with no Shopify store needed:

```
python build/render.py "<theme folder>" <template.json> <out folder> [products.json] "<page title>"
```

Needs `pip install python-liquid`. Per-site touch-ups live in each folder's `overrides.css`.
