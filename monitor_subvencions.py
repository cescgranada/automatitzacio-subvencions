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

def cercar_bopb():
    print("Consultant BOPB (Província i Ajuntament)...")
    # Canal RSS del BOPB filtrat per subvencions
    url = "https://bop.diba.cat/rss.asp?seccio=4.2"
    try:
        res = requests.get(url, timeout=10)
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(res.content, parser=parser)
        items = []
        for item in root.xpath("//item"):
            titol = item.find('title').text
            enllac = item.find('link').text
            # Filtrem perquè a vegades el BOPB és molt genèric
            items.append(f"BOPB/Ajuntament: {titol} ({enllac})")
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
    perfil = """
    Som l'Escola Nou Patufet, una escola cooperativa situada a la Vila de Gràcia (Barcelona). 
    Ens interessen especialment les subvencions i ajuts relacionats amb:
    1. Educació infantil, primària i secundària.
    2. Millores en infraestructures escolars, eficiència energètica o obres de reforma.
    3. Projectes de digitalització i innovació pedagògica.
    4. Ajuts a la contractació, formació del professorat o economia cooperativa.
    5. Subvencions per a menjadors escolars, activitats extraescolars o sortides culturals.
    6. Ajuts de l'Ajuntament de Barcelona o la Generalitat per a entitats del barri de Gràcia.
    Si trobes alguna d'aquestes, explica breument què es demana, el termini i posa l'enllaç.
    """
    
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
    # 1. Recollim dades de les 3 fonts oficials
    # Recorda haver afegit les funcions cercar_dogc(), cercar_boe() i cercar_bopb()
    dades = cercar_dogc() + cercar_boe() + cercar_bopb()
    
    # 2. La IA processa i filtra segons el perfil de l'Escola Nou Patufet
    resum = resumir_amb_ia("\n".join(dades))
    
    # 3. Mostrem el resultat a la consola de GitHub (per a control)
    print(resum)
    
    # 4. Guardem una còpia de seguretat en un fitxer de text
    with open("ultim_resum.txt", "w", encoding="utf-8") as f:
        f.write(resum)
    
    # 5. Enviem el correu definitiu a la teva bústia
    enviar_correu(resum)

if __name__ == "__main__":
    main()
