import requests
import os
import smtplib
import io
import json
from email.mime.text import MIMEText
from lxml import etree
from datetime import datetime
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# 1. CONFIGURACIÓ DE LES CLAUS (GitHub Secrets)
API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)

# ID de la carpeta de Drive que m'has passat
GDRIVE_FOLDER_ID = "14Fgh_2rU43gsiXhaTGE-vAFGEqSoXYfW"

# 2. FUNCIONS PER BUSCAR ALS DIARIS OFICIALS
def cercar_dogc():
    url = "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_ajuts_subvencions_i_beques/index.rss"
    try:
        res = requests.get(url, timeout=10)
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(res.content, parser=parser)
        return [{"titol": i.find('title').text, "link": i.find('link').text, "font": "DOGC"} for i in root.xpath("//item")]
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
                items.append({"titol": titol, "link": link, "font": "BOE"})
        return items
    except: return []

def cercar_bopb():
    url = "https://bop.diba.cat/rss.asp?seccio=4.2"
    try:
        res = requests.get(url, timeout=10)
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(res.content, parser=parser)
        return [{"titol": i.find('title').text, "link": i.find('link').text, "font": "BOPB/Ajuntament"} for i in root.xpath("//item")]
    except: return []

# 3. FUNCIÓ PER GUARDAR EL PDF AL DRIVE
def pujar_a_drive(url_pdf, nom_arxiu):
    creds_json = os.getenv("GDRIVE_CREDENTIALS")
    if not creds_json:
        print("Error: No s'han trobat les credencials de Drive.")
        return
    
    try:
        info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(info)
        service = build('drive', 'v3', credentials=creds)

        response = requests.get(url_pdf, timeout=20)
        fh = io.BytesIO(response.content)

        file_metadata = {'name': nom_arxiu, 'parents': [GDRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(fh, mimetype='application/pdf')
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print(f"✅ Arxiu guardat al Drive amb ID: {file.get('id')}")
    except Exception as e:
        print(f"❌ Error pujant al Drive: {e}")

# 4. LA INTEL·LIGÈNCIA ARTIFICIAL
def resumir_i_processar(llista_anuncis):
    if not llista_anuncis:
        return "Avui no s'ha publicat cap subvenció nova."

    model = genai.GenerativeModel('gemini-1.5-flash')
    text_per_analitzar = "\n".join([f"{a['font']}: {a['titol']} ({a['link']})" for a in llista_anuncis])
    
    perfil = """
    Som l'Escola Nou Patufet, una escola cooperativa de la Vila de Gràcia (Barcelona). 
    Busquem especialment: 
    1. Ajuts per a l'atenció de l'alumnat vulnerable i plans de xoc contra la segregació.
    2. Finançament addicional per a centres (motxilles econòmiques, NESE, equitat).
    3. Subvencions per a infraestructures, digitalització i menjadors.
    4. Convocatòries de l'Ajuntament de Barcelona (Districte de Gràcia) i la Generalitat (Departament d'Educació).
    """
    
    prompt = f"""
    Ets un expert en subvencions. Analitza aquests anuncis:
    {text_per_analitzar}
    
    Basat en aquest perfil: {perfil}
    
    1. Selecciona només les que siguin realment rellevants.
    2. Fes un resum breu en català per a cadascuna.
    3. Al final, indica exactament quins enllaços de PDF s'han de descarregar (posa'ls en una llista separada per comes).
    """
    
    response = model.generate_content(prompt)
    resum = response.text

    # Intentem descarregar els PDFs que la IA ha considerat interessants
    for anunci in llista_anuncis:
        if anunci['link'] in resum:
            nom_net = anunci['titol'][:50].replace("/", "-") + ".pdf"
            pujar_a_drive(anunci['link'], nom_net)

    return resum

# 5. ENVIAMENT DE CORREU
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

# 6. EXECUCIÓ PRINCIPAL
def main():
    print("Iniciant cerca de subvencions...")
    dades = cercar_dogc() + cercar_boe() + cercar_bopb()
    resum = resumir_i_processar(dades)
    
    with open("ultim_resum.txt", "w", encoding="utf-8") as f:
        f.write(resum)
    
    enviar_correu(resum)
    print("Procés finalitzat correctament.")

if __name__ == "__main__":
    main()
