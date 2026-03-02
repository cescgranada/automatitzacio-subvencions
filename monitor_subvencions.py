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
from docx import Document

# 1. CONFIGURACIÓ DE SEGURETAT (GitHub Secrets)
API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)

# ID de la carpeta de Drive de l'Escola Nou Patufet
GDRIVE_FOLDER_ID = "14Fgh_2rU43gsiXhaTGE-vAFGEqSoXYfW"

# 2. FONTS DE DADES (BOE, DOGC, BOPB i EUROPA)
def cercar_dogc():
    url = "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_ajuts_subvencions_i_beques/index.rss"
    try:
        res = requests.get(url, timeout=10)
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(res.content, parser=parser)
        return [{"titol": i.find('title').text, "link": i.find('link').text, "font": "DOGC (Generalitat)"} for i in root.xpath("//item")]
    except: return []

def cercar_europa():
    url = "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_subvencions_internacionals/index.rss"
    try:
        res = requests.get(url, timeout=10)
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(res.content, parser=parser)
        return [{"titol": i.find('title').text, "link": i.find('link').text, "font": "EUROPA / Internacional"} for i in root.xpath("//item")]
    except: return []

def cercar_boe():
    avui = datetime.now().strftime("%Y%m%d")
    url = f"https://www.boe.es/diario_boe/xml.php?id=BOE-S-{avui}"
    try:
        res = requests.get(url, timeout=10)
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(res.content, parser=parser)
        items = []
        for anunci in root.xpath("//seccion[@num='3']//item"):
            titol = anunci.find("titulo").text
            if any(p in titol.lower() for p in ["subvención", "ayuda", "convocatoria", "subvencions", "beca"]):
                link = "https://www.boe.es" + anunci.find("url_pdf").text
                items.append({"titol": titol, "link": link, "font": "BOE (Estat)"})
        return items
    except: return []

def cercar_bopb():
    url = "https://bop.diba.cat/rss.asp?seccio=4.2"
    try:
        res = requests.get(url, timeout=10)
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(res.content, parser=parser)
        return [{"titol": i.find('title').text, "link": i.find('link').text, "font": "BOPB (Barcelona)"} for i in root.xpath("//item")]
    except: return []

# 3. GESTIÓ DE DOCUMENTS (WORD I DRIVE)
def crear_fitxa_word(dades):
    try:
        doc = Document('plantilla_subvencio.docx')
        for p in doc.paragraphs:
            for clau in ['titol', 'organisme', 'import', 'termini', 'resum', 'accions']:
                placeholder = f"{{{{{clau}}}}}"
                if placeholder in p.text:
                    p.text = p.text.replace(placeholder, str(dades.get(clau, 'No especificat')))
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f"Error creant fitxa Word: {e}")
        return None

def pujar_a_drive(contingut, nom_arxiu, mimetype='application/pdf'):
    creds_json = os.getenv("GDRIVE_CREDENTIALS")
    if not creds_json: return
    try:
        info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(info)
        service = build('drive', 'v3', credentials=creds)
        
        fh = io.BytesIO(contingut) if isinstance(contingut, bytes) else contingut
        file_metadata = {'name': nom_arxiu, 'parents': [GDRIVE_FOLDER_ID]}
        media = MediaIoBaseUpload(fh, mimetype=mimetype, resumable=True)
        service.files().create(body=file_metadata, media_body=media).execute()
        print(f"✅ Guardat al Drive: {nom_arxiu}")
    except Exception as e:
        print(f"❌ Error Drive ({nom_arxiu}): {e}")

# 4. INTEL·LIGÈNCIA ARTIFICIAL (ANÀLISI I FILTRAT)
def processar_subvencions(llista):
    if not llista: return "Avui no s'ha trobat cap publicació als diaris oficials.", []
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    perfil = """
    Som l'Escola Nou Patufet, una escola cooperativa de la Vila de Gràcia (Barcelona). 
    Busquem especialment:
    1. Ajuts per a l'atenció de l'alumnat vulnerable i fons de motxilles econòmiques (Pla de Xoc).
    2. Subvencions del Departament d'Educació, Ajuntament de Barcelona i Districte de Gràcia.
    3. Fons europeus (Erasmus+, Next Generation) per a digitalització, sostenibilitat o innovació.
    4. Ajuts per a infraestructures escolars, menjadors i economia cooperativa.
    """
    
    prompt = f"""
    Analitza aquesta llista de publicacions: {json.dumps(llista)}
    Perfil de l'escola: {perfil}
    
    Si una subvenció és realment rellevant, genera un llistat en format JSON pur (sense markdown) on cada objecte tingui:
    "titol", "organisme", "import", "termini", "resum", "accions", "link_pdf".
    Si no n'hi ha cap de rellevant, respon exactament: []
    """
    
    response = model.generate_content(prompt)
    try:
        net = response.text.replace("```json", "").replace("```", "").strip()
        interessants = json.loads(net)
    except:
        return "Error en l'anàlisi de dades o cap subvenció rellevante avui.", []

    for s in interessants:
        try:
            # 1. Guardem PDF original
            pdf_res = requests.get(s['link_pdf'], timeout=20)
            nom_base = s['titol'][:40].replace("/", "-").replace(" ", "_")
            pujar_a_drive(pdf_res.content, f"ORIGINAL_{nom_base}.pdf")
            
            # 2. Creem i guardem Fitxa Word
            word_buf = crear_fitxa_word(s)
            if word_buf:
                pujar_a_drive(word_buf, f"FITXA_{nom_base}.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        except Exception as e:
            print(f"Error processant {s.get('titol')}: {e}")

    return f"S'han trobat {len(interessants)} subvencions rellevants.", interessants

# 5. ENVIAMENT DE NOTIFICACIÓ
def enviar_correu(text):
    sender = os.getenv("EMAIL_USER")
    passw = os.getenv("EMAIL_PASS")
    dest = os.getenv("EMAIL_RECEIVER")
    if not all([sender, passw, dest]): return
    
    msg = MIMEText(text, 'plain', 'utf-8')
    msg['Subject'] = f"Alerta Subvencions Nou Patufet - {datetime.now().strftime('%d/%m/%Y')}"
    msg['From'] = sender
    msg['To'] = dest

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, passw)
            server.sendmail(sender, dest, msg.as_string())
    except Exception as e:
        print(f"Error enviant mail: {e}")

# 6. EXECUCIÓ PRINCIPAL
def main():
    print("Iniciant escaneig (BOE, DOGC, BOPB, EUROPA)...")
    dades = cercar_dogc() + cercar_europa() + cercar_boe() + cercar_bopb()
    resum_text, interessants = processar_subvencions(dades)
    
    if interessants:
        cos_mail = "S'han trobat oportunitats per a la Nou Patufet:\n\n"
        for s in interessants:
            cos_mail += f"- {s['titol']}\n  Import: {s['import']}\n  Link: {s['link_pdf']}\n\n"
        cos_mail += "Documents i fitxes guardades al Drive."
        enviar_correu(cos_mail)
    else:
        enviar_correu("Avui no hi ha novetats rellevants per a l'escola.")

if __name__ == "__main__":
    main()
