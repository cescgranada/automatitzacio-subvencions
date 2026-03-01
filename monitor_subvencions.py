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

# ID de la teva carpeta de Drive de l'escola
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
    # Font específica de la Generalitat per a fons europeus i internacionals
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
                if f'{{{{{clau}}}}}' in p.text:
                    p.text = p.text.replace(f'{{{{{clau}}}}}', str(dades.get(clau, 'No especificat')))
        
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
    except Exception as e:
        print(f"Error pujant {nom_arxiu} a Drive: {e}")

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
    4. Ajuts per a infraestructures escolars, menjadors i economia
