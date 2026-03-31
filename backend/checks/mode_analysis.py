## Ersetze die get_text-Funktion in mode_analysis.py:

def get_text(soup: BeautifulSoup) -> str:
    """Extrahiert sichtbaren Text ohne Nav/Footer/Scripts."""
    from bs4 import NavigableString, Tag
    soup_copy = BeautifulSoup(str(soup), "html.parser")
    for tag in soup_copy(["nav", "footer", "script", "style", "header"]):
        if isinstance(tag, Tag):
            tag.decompose()
    return soup_copy.get_text(" ", strip=True).lower()
