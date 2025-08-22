from bs4 import BeautifulSoup
import re 
import requests
from io import BytesIO

def fetch_text(url: str, timeout: int = 30) -> str:
    try:
        response = requests.get(url, headers={"User-Agent":"sparser/1.0"}, timeout=timeout)
        response.raise_for_status()
        #Extrait le type de page 
        ctype = (response.headers.get("Content-Type") or "").lower()
        if "pdf" in ctype:
            #Convertir en fichier 
            pdf_file = BytesIO(response.content)
            return text_from_pdf(pdf_file)
        return text_from_html(response.content)
    except:
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
            # Parcourt chaque page
            for page_number, page in enumerate(pdf.pages, start=1):
                # Essaie d'extraire le texte “natif”
                page_text = page.extract_text() or ""
                #text += f"\n--- Page {page_number} ---\n"
                text += page_text
    return text