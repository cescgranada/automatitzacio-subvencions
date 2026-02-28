import requests
import os
from lxml import etree
from datetime import datetime
import google.generativeai as genai

# Configura la IA (GitHub Actions agafarà la clau automàticament)
API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)

def cercar_dogc():
    url = "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_ajuts_subvencions_i_beques/index.rss"
    try:
        res = requests.get(url, timeout=10)
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(res.content, parser=parser)
        items = [f"DOGC: {i.find('title').text} ({i.find('link').text})" for i in root.xpath("//item")[:15]]
        return items
    except: return []

def cercar_boe():
    avui = datetime.now().strftime("%Y%m%d")
    url = f"https://www.boe.es/diario_boe/xml.php?id=BOE-S-{avui}"
    try:
        res = requests.get(url, timeout=10)
        if res.status_code != 200: return []
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(res.content, parser=parser)
        items = []
        for anunci in root.xpath("//seccion[@num='3']//item"):
            titol = anunci.find("titulo").text
            if any(p in titol.lower() for p in ["subvención", "ayuda", "convocatoria", "subvencions"]):
                link = "https://www.boe.es" + anunci.find("url_pdf").text
                items.append(f"BOE: {titol} ({link})")
        return items
    except: return []

def resumir_amb_ia(llista_text):
    if not llista_text: return "Avui no hi ha subvencions noves."
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # Aquí pots personalitzar el perfil!
    perfil = "Sóc una PIME de tecnologia a Catalunya interessada en digitalització i sostenibilitat."
    
    prompt = f"""
    Ets un expert en subvencions. He trobat aquestes publicacions avui al BOE i DOGC:
    {llista_text}
    
    Basat en aquest perfil: {perfil}
    Fes un resum executiu:
    1. Selecciona només les que realment encaixin.
    2. Explica breument què ofereixen i posa l'enllaç.
    3. Si no n'hi ha cap d'interessant, digues-ho.
    Respon en català i de forma molt concisa.
    """
    
    response = model.generate_content(prompt)
    return response.text

def main():
    dades = cercar_dogc() + cercar_boe()
    resum = resumir_amb_ia("\n".join(dades))
    
    print(resum)
    with open("ultim_resum.txt", "w", encoding="utf-8") as f:
        f.write(resum)

if __name__ == "__main__":
    main()
