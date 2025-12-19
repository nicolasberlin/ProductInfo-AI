from bs4 import BeautifulSoup
import re 
import requests
from io import BytesIO
import os 
import sys

def fetch_text(url: str, timeout: int = 30) -> str:
        # --- Cas chemin local (minimal) ---
    #print(f"\x1b[34m[fetch_text] input: {url}\x1b[0m", file=sys.stderr)
    
    if os.path.exists(url):
        with open(url, "rb") as f:
            data = f.read()
        if data.startswith(b"%PDF-"):
            return text_from_pdf(BytesIO(data))
        return text_from_html(data)

    try:
        response = requests.get(url, headers={"User-Agent":"sparser/1.0"}, timeout=timeout)
        response.raise_for_status()
        # Extract content type
        ctype = (response.headers.get("Content-Type") or "").lower()
        if "pdf" in ctype:
            #Convertir en fichier 
            pdf_file = BytesIO(response.content)
            return text_from_pdf(pdf_file)
        return text_from_html(response.content)
    except Exception as e:
        print("Error fetching URL", url)
        print("Error details:", e)
        return ""
        
def text_from_html(html) -> str:
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(["script", "style", "noscript", "iframe", "footer"]):
        tag.decompose()

    txt = soup.get_text(separator="\n", strip=True)
    # Garde une ligne vide propre entre paragraphes
    txt = re.sub(r"\n{2,}", "\n\n", txt)
    return txt

import pdfplumber

def text_from_pdf(pdf_file) -> str:
    text = ""
    with pdfplumber.open(pdf_file) as pdf:
            # Iterate each page
            for page_number, page in enumerate(pdf.pages, start=1):
                # Essaie d'extraire le texte “natif”
                page_text = page.extract_text() or ""
                print(f"[text_from_pdf] page {page_text} length={len(page_text)}", file=sys.stderr)
                # text += f"\n--- Page {page_number} ---\n"
                text += page_text
    return text

def text_pages_from_pdf(pdf_file) -> list[str]:
    # print(f"\x1b[34m[text_pages_from_pdf] input: {pdf_file}\x1b[0m", file=sys.stderr)
    pages = []
    with pdfplumber.open(pdf_file) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text(x_tolerance=3, y_tolerance=8) or ""
            pages.append(page_text)

    # print number of pages and a compact per-page preview (blue)
    BLUE = "\x1b[34m"
    RESET = "\x1b[0m"
    # print(f"{BLUE}[text_pages_from_pdf] extracted {len(pages)} pages{RESET}", file=sys.stderr)
    for i, p in enumerate(pages, start=1):
        plen = len(p or "")
        # show full page only if small, otherwise a truncated preview
        if plen <= 300:
            content_preview = p
        else:
            content_preview = (p[:300].rstrip() + "…")
        # print(f"{BLUE}[text_pages_from_pdf] page {i} length={plen}{RESET}", file=sys.stderr)
        #print(f"{BLUE}{content_preview}{RESET}", file=sys.stderr)
    return pages


def fetch_text_pages(url: str, timeout: int = 30) -> list[str]:
    # print(f"\x1b[34m[fetch_text_pages] input: {url}\x1b[0m", file=sys.stderr)
    if os.path.exists(url):
        with open(url, "rb") as f:
            data = f.read()
        if data.startswith(b"%PDF-"):
            print("Detected PDF file", file=sys.stderr)
            return text_pages_from_pdf(BytesIO(data))
        return [text_from_html(data)]

    try:
        response = requests.get(url, headers={"User-Agent":"sparser/1.0"}, timeout=timeout)
        response.raise_for_status()
        ctype = (response.headers.get("Content-Type") or "").lower()
        if "pdf" in ctype:
            pdf_file = BytesIO(response.content)
            return text_pages_from_pdf(pdf_file)
        return [text_from_html(response.content)]
    except Exception as e:
        print("Error fetching URL", url)
        print("Error details:", e)
        return []
