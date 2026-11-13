"""Shared page shell: reuse head/style/theme/footer scripts of about.html for generated pages."""
import json, pathlib, re

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = "https://bazarnama.github.io"


def shell(name, title, desc, schema_type, schema_name, body, css="", script=""):
    src = (ROOT / "about.html").read_text(encoding="utf-8")
    head, rest = src.split("<body>", 1)
    tail = rest[rest.index("<script>(()=>{'use strict'"):]
    ld = json.dumps({"@context": "https://schema.org", "@type": schema_type, "name": schema_name,
                     "url": f"{BASE}/{name}", "inLanguage": "fa-IR", "description": desc}, ensure_ascii=False)
    head = re.sub(r"<title>.*?</title>", lambda m: f"<title>{title}</title>", head, flags=re.S)
    head = head.replace("about.html", name)
    for k in ('name="description" content="', 'property="og:description" content="', 'name="twitter:description" content="'):
        head = re.sub("(" + re.escape(k) + ")[^\"]*", lambda m: m.group(1) + desc, head)
    for k in ('og:title" content="', 'twitter:title" content="'):
        head = re.sub("(" + re.escape(k) + ")[^\"]*", lambda m: m.group(1) + title, head)
    head = re.sub(r'<script type="application/ld\+json">.*?</script>',
                  lambda m: f'<script type="application/ld+json">{ld}</script>', head, count=1, flags=re.S)
    head = head.replace("</head>", f"<style>{css}</style></head>")
    (ROOT / name).write_text(head + '<body><main class="wrap">\n' + body + script + tail, encoding="utf-8")
