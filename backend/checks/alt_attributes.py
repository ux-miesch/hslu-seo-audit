from bs4 import BeautifulSoup
from urllib.parse import urljoin
from whitelist import ALT_ATTRIBUTE_FILENAME_WHITELIST, ALT_ATTRIBUTE_EXTENSION_WHITELIST


def _is_whitelisted(src: str) -> bool:
    clean = src.split("?")[0].split("#")[0]
    filename = clean.split("/")[-1].lower()
    for ext in ALT_ATTRIBUTE_EXTENSION_WHITELIST:
        if filename.endswith(ext.lower()):
            return True
    return filename in [f.lower() for f in ALT_ATTRIBUTE_FILENAME_WHITELIST]


def check_alt_attributes(soup: BeautifulSoup, base_url: str) -> dict:
    issues = []
    warnings = []
    passed = []
    data = {"images": [], "videos": [], "iframes": [], "pdfs": []}

    # ── BILDER ────────────────────────────────────────────────────────────
    images = soup.find_all("img")
    for img in images:
        src = img.get("src", "")
        alt = img.get("alt")
        absolute_src = urljoin(base_url, src) if src else ""
        if _is_whitelisted(absolute_src or src):
            continue
        img_data = {"src": absolute_src, "alt": alt}
        data["images"].append(img_data)
        if alt is None:
            issues.append({
                "code": "IMG_MISSING_ALT",
                "message": f"Bild ohne alt-Attribut: {absolute_src or '[kein src]'}",
                "severity": "critical",
                "src": absolute_src,
            })
        elif alt.strip() == "":
            pass
        elif len(alt.strip()) < 5:
            warnings.append({
                "code": "IMG_ALT_TOO_SHORT",
                "message": f"Alt-Text sehr kurz ({len(alt.strip())} Zeichen): \"{alt}\" → {absolute_src}",
                "severity": "warning",
                "src": absolute_src,
                "alt": alt,
            })
        elif alt.lower().startswith(("bild", "image", "foto", "photo", "img", "grafik")):
            warnings.append({
                "code": "IMG_ALT_GENERIC",
                "message": f"Alt-Text nichtssagend: \"{alt}\" → {absolute_src}",
                "severity": "warning",
                "src": absolute_src,
                "alt": alt,
            })
        else:
            passed.append({"code": "IMG_ALT_OK", "message": f"Alt-Text vorhanden: \"{alt[:60]}\"", "src": absolute_src, "alt": alt})

    if not images:
        passed.append({"code": "NO_IMAGES", "message": "Keine Bilder auf der Seite gefunden."})

    # ── VIDEOS ────────────────────────────────────────────────────────────
    videos = soup.find_all("video")
    for video in videos:
        src = video.get("src", "")
        aria_label = video.get("aria-label", "")
        title = video.get("title", "")
        absolute_src = urljoin(base_url, src) if src else ""
        data["videos"].append({"src": absolute_src, "aria_label": aria_label, "title": title})
        if not aria_label and not title:
            issues.append({
                "code": "VIDEO_MISSING_LABEL",
                "message": f"Video ohne aria-label oder title: {absolute_src or '[kein src]'}",
                "severity": "warning",
                "src": absolute_src,
            })
        else:
            passed.append({"code": "VIDEO_LABEL_OK", "message": f"Video mit Label: \"{(aria_label or title)[:60]}\"", "src": absolute_src, "label": aria_label or title})

    # ── IFRAMES ───────────────────────────────────────────────────────────
    IGNORE_IFRAME_DOMAINS = {"googletagmanager.com", "google.com/recaptcha", "doubleclick.net"}
    iframes = soup.find_all("iframe")
    for iframe in iframes:
        src = iframe.get("src", "")
        title = iframe.get("title", "")
        aria_label = iframe.get("aria-label", "")
        if any(domain in src for domain in IGNORE_IFRAME_DOMAINS):
            continue
        data["iframes"].append({"src": src, "title": title})
        if not title and not aria_label:
            issues.append({
                "code": "IFRAME_MISSING_TITLE",
                "message": f"iframe ohne title-Attribut: {src or '[kein src]'}",
                "severity": "warning",
                "src": src,
            })
        else:
            passed.append({"code": "IFRAME_TITLE_OK", "message": f"iframe mit title: \"{(title or aria_label)[:60]}\"", "src": src, "label": title or aria_label})

    # ── PDF-LINKS ─────────────────────────────────────────────────────────
    pdf_links = [
        a for a in soup.find_all("a", href=True)
        if a["href"].lower().endswith(".pdf") or "pdf" in a["href"].lower()
    ]
    for a in pdf_links:
        href = a["href"]
        anchor_text = a.get_text(strip=True)
        absolute_href = urljoin(base_url, href)
        aria_label = a.get("aria-label", "")
        data["pdfs"].append({"href": absolute_href, "anchor_text": anchor_text, "aria_label": aria_label})
        if not anchor_text and not aria_label:
            issues.append({
                "code": "PDF_MISSING_TEXT",
                "message": f"PDF-Link ohne Ankertext oder aria-label: {absolute_href}",
                "severity": "warning",
                "href": absolute_href,
            })
        elif anchor_text.lower() in ("pdf", "download", "hier", "here", "klicken", "click"):
            warnings.append({
                "code": "PDF_GENERIC_TEXT",
                "message": f"PDF-Link mit nichtssagendem Ankertext: \"{anchor_text}\" → {absolute_href}",
                "severity": "warning",
                "href": absolute_href,
            })
        else:
            passed.append({"code": "PDF_TEXT_OK", "message": f"PDF-Link mit beschreibendem Text: \"{anchor_text[:60]}\"", "href": absolute_href, "anchor_text": anchor_text})

    data["summary"] = {
        "total_images": len(images),
        "total_videos": len(videos),
        "total_iframes": len(iframes),
        "total_pdfs": len(pdf_links),
    }
    return _build_result(issues, warnings, passed, data)


def _build_result(issues, warnings, passed, data) -> dict:
    _DEDUCTIONS = {
        "IMG_MISSING_ALT": 20,
        "IMG_ALT_TOO_SHORT": 10, "IMG_ALT_GENERIC": 10,
        "VIDEO_MISSING_LABEL": 10,
        "IFRAME_MISSING_TITLE": 5, "PDF_MISSING_TEXT": 5, "PDF_GENERIC_TEXT": 5,
    }
    score = 100
    for entry in issues + warnings:
        score -= _DEDUCTIONS.get(entry.get("code", ""), 0)
    score = max(0, score)
    return {"score": score, "issues": issues, "warnings": warnings, "passed": passed, "data": data}
