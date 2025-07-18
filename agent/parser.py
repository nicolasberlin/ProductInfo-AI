import pdfplumber


def extract_text(path: str) -> str:
    """
    Extrait le texte de tout le PDF, page par page.

    :param path: chemin vers le fichier PDF
    :return: texte brut de toutes les pages
    """
    text = ""
    # Ouvre le PDF avec pdfplumber
    with pdfplumber.open(path) as pdf:
        # Parcourt chaque page
        for page_number, page in enumerate(pdf.pages, start=1):
            # Essaie d'extraire le texte “natif”
            page_text = page.extract_text() or ""
            text += f"\n--- Page {page_number} ---\n"
            text += page_text
            
    return text


def find_information(patent: str, product: str):

    #if patent and product in cache then retur, else 
    


    

