import requests
import os
import smtplib
from email.mime.text import MIMEText
from lxml import etree
from datetime import datetime
import google.generativeai as genai

# 1. CONFIGURACIÓ DE LA IA
API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)

# 2. FONTS DE DADES (DOGC, BOE, BOPB)
def cercar_dogc():
    url = "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_ajuts_subvencions_i_beques/index.rss"
    try:
        res = requests.get(url, timeout=10)
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(res.content, parser=parser)
        return [f"DOGC: {i.find('title').text} ({i.find('link').text})" for i in root.xpath("//item")]
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

def cercar_bopb():
    url = "https://bop.diba.cat/rss.asp?seccio=4.2"
    try:
        res = requests.get(url, timeout=10)
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(res.content, parser=parser)
        return [f"BOPB/Ajuntament: {i.find('title').text} ({i.find('link').text})" for i in root.xpath("//item")]
    except: return []

# 3. EL FILTRE INTEL·LIGENT
def resumir_amb_ia(llista_text):
    if not llista_text: return "Avui no hi ha subvencions noves a cap diari oficial."
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    perfil = """
    Som l'Escola Nou Patufet, una escola cooperativa de la Vila de Gràcia (Barcelona). 
    Busquem ajuts per a: educació (infantil a secundària), infraestructures escolars, 
    digitalització, menjadors, extraescolars, cultura, economia cooperativa i 
    subvencions del Districte de Gràcia o l'Ajuntament de Barcelona.
    """
    
    prompt = f"Ets un expert en subvencions. He trobat això:\n{llista_text}\nBasat en el perfil: {perfil}, selecciona les rellevants i fes un resum breu en català amb els enllaços."
    
    response = model.generate_content(prompt)
    return response.text

# 4. L'ENVIAMENT
def enviar_correu(contingut):
    sender = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    receiver = os.getenv("EMAIL_RECEIVER")
    
    if not all([sender, password, receiver]): return
    
    msg = MIMEText(contingut, 'plain', 'utf-8')
    msg['Subject'] = f"Subvencions Escola Nou Patufet - {datetime.now().strftime('%d/%m/%Y')}"
    msg['From'] = sender
    msg['To'] = receiver

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, password)
            server.sendmail(sender, receiver, msg.as_string())
    except Exception as e:
        print(f"Error enviant correu: {e}")

# 5. EL TEU MAIN()
def main():
    dades = cercar_dogc() + cercar_boe() + cercar_bopb()
    resum = resumir_amb_ia("\n".join(dades))
    print(resum)
    with open("ultim_resum.txt", "w", encoding="utf-8") as f:
        f.write(resum)
    enviar_correu(resum)

if __name__ == "__main__":
    main()
