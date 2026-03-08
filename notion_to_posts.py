import os
import json
import requests
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
NOTION_TOKEN  = os.environ["NOTION_TOKEN"]
DATABASE_ID   = os.environ["NOTION_DATABASE_ID"]

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

MONTHS_ES = {
    "January": "enero", "February": "febrero", "March": "marzo",
    "April": "abril",   "May": "mayo",          "June": "junio",
    "July": "julio",    "August": "agosto",     "September": "septiembre",
    "October": "octubre","November": "noviembre","December": "diciembre",
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def plain(rich_text_array):
    """Extract plain text from a Notion rich_text array."""
    return "".join(t["plain_text"] for t in (rich_text_array or []))


def format_date_es(date_str):
    """'2026-03-10' → '10 de marzo de 2026'"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    month_es = MONTHS_ES[dt.strftime("%B")]
    return f"{dt.day} de {month_es} de {dt.year}"


def slugify(text, date_str):
    import re
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]
    return slug + "-" + date_str.replace("-", "")[:8]


def get_blocks(page_id):
    """Fetch all blocks for a page (handles pagination)."""
    blocks = []
    url = f"https://api.notion.com/v1/blocks/{page_id}/children"
    params = {}
    while True:
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        blocks.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        params["start_cursor"] = data["next_cursor"]
    return blocks


def blocks_to_content(blocks):
    """
    Convert Notion blocks to the content array format used by post.html.
    Supports: paragraph, heading_1/2/3, bulleted/numbered list, image,
              divider, quote, callout, code.
    """
    content = []
    list_buffer = []   # collect consecutive list items
    list_type = None   # "ul" or "ol"

    def flush_list():
        if not list_buffer:
            return
        tag = "ul" if list_type == "ul" else "ol"
        items_html = "".join(f"<li>{item}</li>" for item in list_buffer)
        content.append(
            f"<{tag} style='padding-left:18px;margin:8px 0;'>{items_html}</{tag}>"
        )
        list_buffer.clear()

    H_STYLE = "font-family:'Press Start 2P',monospace;color:#cc44ff;margin:16px 0 8px;"
    CODE_STYLE = (
        "background:#0d001a;border:1px solid #8a2be2;padding:12px;"
        "font-size:10px;overflow-x:auto;white-space:pre-wrap;color:#00ff00;"
    )
    QUOTE_STYLE = (
        "border-left:3px solid #8a2be2;padding:6px 12px;"
        "background:#1a0030;color:#ccc;font-style:italic;margin:10px 0;"
    )
    CALLOUT_STYLE = (
        "background:#1a0030;border:1px solid #8a2be2;padding:10px 14px;"
        "border-radius:4px;margin:10px 0;"
    )

    for block in blocks:
        btype = block["type"]

        # ── Lists (buffer until type changes) ────────────────────────────
        if btype == "bulleted_list_item":
            if list_type != "ul":
                flush_list()
                list_type = "ul"
            text = plain(block["bulleted_list_item"]["rich_text"])
            if text:
                list_buffer.append(text)
            continue

        if btype == "numbered_list_item":
            if list_type != "ol":
                flush_list()
                list_type = "ol"
            text = plain(block["numbered_list_item"]["rich_text"])
            if text:
                list_buffer.append(text)
            continue

        # ── Non-list block → flush any pending list ───────────────────────
        flush_list()
        list_type = None

        if btype == "paragraph":
            text = plain(block["paragraph"]["rich_text"])
            if text:
                content.append(text)

        elif btype in ("heading_1", "heading_2", "heading_3"):
            sizes = {"heading_1": "11px", "heading_2": "9px", "heading_3": "8px"}
            text = plain(block[btype]["rich_text"])
            if text:
                content.append(
                    f"<h3 style='{H_STYLE}font-size:{sizes[btype]};'>{text}</h3>"
                )

        elif btype == "image":
            img = block["image"]
            url_img = (
                img.get("file", {}).get("url", "")
                or img.get("external", {}).get("url", "")
            )
            caption = plain(img.get("caption", []))
            cap_html = (
                f"<p style='font-size:9px;color:#888;text-align:center;margin:2px 0 10px;'>"
                f"{caption}</p>"
                if caption else ""
            )
            if url_img:
                content.append(
                    f"<img src='{url_img}' alt='{caption}' "
                    f"style='width:100%;border:2px solid #8a2be2;"
                    f"image-rendering:pixelated;margin:10px 0 2px;'>"
                    + cap_html
                )

        elif btype == "divider":
            content.append(
                "<hr style='border:none;border-top:2px solid #8a2be2;margin:16px 0;'>"
            )

        elif btype == "quote":
            text = plain(block["quote"]["rich_text"])
            if text:
                content.append(f"<blockquote style='{QUOTE_STYLE}'>{text}</blockquote>")

        elif btype == "callout":
            text = plain(block["callout"]["rich_text"])
            emoji = block["callout"].get("icon", {}).get("emoji", "💡")
            if text:
                content.append(
                    f"<div style='{CALLOUT_STYLE}'>{emoji} {text}</div>"
                )

        elif btype == "code":
            text = plain(block["code"]["rich_text"])
            lang = block["code"].get("language", "")
            if text:
                content.append(
                    f"<pre style='{CODE_STYLE}'><code class='language-{lang}'>"
                    f"{text}</code></pre>"
                )

        # video embed (YouTube only for simplicity)
        elif btype == "video":
            vid = block["video"]
            url_vid = (
                vid.get("external", {}).get("url", "")
                or vid.get("file", {}).get("url", "")
            )
            # Try to extract a YouTube video ID
            import re
            yt_match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url_vid)
            if yt_match:
                vid_id = yt_match.group(1)
                content.append(
                    f"<div style='position:relative;padding-bottom:56.25%;height:0;overflow:hidden;margin:12px 0;'>"
                    f"<iframe style='position:absolute;top:0;left:0;width:100%;height:100%;border:2px solid #8a2be2;' "
                    f"src='https://www.youtube-nocookie.com/embed/{vid_id}' "
                    f"frameborder='0' allowfullscreen></iframe></div>"
                )

    flush_list()  # flush any list still buffered at end of page
    return content


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("Querying Notion database…")

    query_body = {
        "filter": {
            "property": "Published",
            "checkbox": {"equals": True}
        },
        "sorts": [
            {"property": "date", "direction": "descending"}
        ]
    }

    resp = requests.post(
        f"https://api.notion.com/v1/databases/{DATABASE_ID}/query",
        headers=HEADERS,
        json=query_body,
    )
    resp.raise_for_status()
    pages = resp.json().get("results", [])
    print(f"Found {len(pages)} published post(s).")

    posts = []
    for page in pages:
        props    = page["properties"]
        page_id  = page["id"]

        # ── Required fields ───────────────────────────────────────────────
        title_en = plain(props.get("Title", {}).get("title", []))
        raw_date = (
            props.get("date", {}).get("date", {}) or {}
        ).get("start", "")

        if not title_en:
            print(f"  ⚠  Skipping page {page_id} — no title.")
            continue
        if not raw_date:
            print(f"  ⚠  Skipping '{title_en}' — no date set.")
            continue

        dt       = datetime.strptime(raw_date, "%Y-%m-%d")
        date_en  = dt.strftime("%B %d, %Y")
        date_es  = format_date_es(raw_date)

        # ── Optional metadata fields ──────────────────────────────────────
        title_es   = plain(props.get("title_es",   {}).get("rich_text", [])) or title_en
        excerpt_en = plain(props.get("excerpt_en", {}).get("rich_text", [])) or ""
        excerpt_es = plain(props.get("excerpt_es", {}).get("rich_text", [])) or excerpt_en
        thumbnail  = plain(props.get("thumbnail",  {}).get("rich_text", [])) or "placeholder_thumbnail.png"
        tags       = [t["name"] for t in props.get("tags", {}).get("multi_select", [])]

        # ── Page body — fetch blocks ──────────────────────────────────────
        print(f"  Fetching blocks for: {title_en}")
        all_blocks = get_blocks(page_id)

        # Split EN and ES blocks by a divider that separates the two langs.
        # Convention: write EN content first, add a Divider block, then ES content.
        # If no divider is found, the same content is used for both languages.
        divider_index = next(
            (i for i, b in enumerate(all_blocks) if b["type"] == "divider"),
            None,
        )

        if divider_index is not None:
            en_blocks = all_blocks[:divider_index]
            es_blocks = all_blocks[divider_index + 1:]
            print(f"    ↳ Found divider at block {divider_index}: {len(en_blocks)} EN blocks, {len(es_blocks)} ES blocks")
        else:
            en_blocks = all_blocks
            es_blocks = all_blocks
            print(f"    ↳ No divider found — using same content for both languages")

        content_en = blocks_to_content(en_blocks)
        content_es = blocks_to_content(es_blocks)

        posts.append({
            "id":         slugify(title_en, raw_date),
            "date":       raw_date,
            "date_en":    date_en,
            "date_es":    date_es,
            "thumbnail":  thumbnail,
            "title_en":   title_en,
            "title_es":   title_es,
            "excerpt_en": excerpt_en,
            "excerpt_es": excerpt_es,
            "content_en": content_en,
            "content_es": content_es,
            "tags":       tags,
        })

    output = {"posts": posts}
    with open("posts.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✓ posts.json written with {len(posts)} post(s).")


if __name__ == "__main__":
    main()
