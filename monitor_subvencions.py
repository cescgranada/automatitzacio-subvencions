import requests
import os
import smtplib
import io
import json
import time
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from lxml import etree
from datetime import datetime
from google import genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from docx import Document

# 1. CONFIGURACIÓ
API_KEY = os.getenv("GEMINI_API_KEY")
SCRAPINGBEE_API_KEY = os.getenv("SCRAPER_API_KEY") 
client = genai.Client(api_key=API_KEY)
GDRIVE_FOLDER_ID = "14Fgh_2rU43gsiXhaTGE-vAFGEqSoXYfW"
HISTORIAL_FILE = "historial_subvencions.json"

# 2. MEMÒRIA
def carregar_historial():
    if os.path.exists(HISTORIAL_FILE):
        try:
            with open(HISTORIAL_FILE, "r", encoding="utf-8") as f: return json.load(f)
        except: return []
    return []

def guardar_historial(llista_nova):
    h = carregar_historial()
    actualitzat = list(set(h + llista_nova))[-500:]
    with open(HISTORIAL_FILE, "w", encoding="utf-8") as f: json.dump(actualitzat, f)

# 3. CERCA DE FONTS AMPLIADA (AMB URL CARULLA CORREGIDA)
def cercar_fonts():
    session = requests.Session()
    totes = []; ok = []; fails = []
    
    fonts_config = [
        ("CIDO (DOGC, BOPB i Europa)", "https://cido.diba.cat/subvencions"),
        ("BOE Estat", f"https://www.boe.es/diario_boe/xml.php?id=BOE-S-{datetime.now().strftime('%Y%m%d')}"),
        ("Fundació la Caixa", "https://fundacionlacaixa.org/ca/convocatories-socials"),
        ("Fundació Bofill", "https://fundaciobofill.cat/crides"),
        ("EduCaixa", "https://educaixa.org/ca/convocatories"),
        # URL de la Carulla actualitzada a l'arrel per evitar errors 404
        ("Fundació Carulla (Cultura i Educació)", "https://fundaciocarulla.cat/"),
        ("Fundació Banc Sabadell (Cultura/Innovació)", "https://www.fundacionbancosabadell.com/convocatorias/"),
        ("Coòpolis (Economia Social BCN)", "https://www.bcn.ateneucooperatiu.cat/noticies/")
    ]

    for nom, url in fonts_config:
        try:
            if SCRAPINGBEE_API_KEY:
                payload = {'api_key': SCRAPINGBEE_API_KEY, 'url': url, 'render_js': 'false'}
                res = session.get('https://app.scrapingbee.com/api/v1/', params=payload, timeout=60)
            else:
                headers = {'User-Agent': 'Mozilla/5.0'}
                res = session.get(url, timeout=35, headers=headers)

            if res.status_code == 200:
                ok.append(nom)
                
                if "xml" in url or "boe" in url:
                    parser = etree.XMLParser(recover=True)
                    root = etree.fromstring(res.content, parser=parser)
                    items = root.xpath("//item") or root.xpath("//anuncio")
                    for i in items[:15]:
                        t = i.findtext('title') or i.findtext('titulo') or "Sense títol"
                        l = i.findtext('link') or (("https://www.boe.es" + i.findtext('url_pdf')) if i.findtext('url_pdf') else url)
                        totes.append({"titol": t, "link": l, "font": nom})
                else:
                    soup = BeautifulSoup(res.text, 'html.parser')
                    paraules_clau = [
                        'ajut', 'subvenció', 'beca', 'convocatòria', 'resolució', 'programa', 
                        'premi', 'crida', 'suport', 'dotació', 'cooperativa', 'gènere', 
                        'pedagògic', 'educació', 'innovació'
                    ]
                    for element in soup.find_all(['a', 'h2', 'h3', 'h4']):
                        txt = element.get_text().strip()
                        if len(txt) > 25 and any(k in txt.lower() for k in paraules_clau):
                            link = element.get('href') if element.name == 'a' else url
                            if link and not link.startswith('http'): 
                                # Ens assegurem de muntar bé l'enllaç si és relatiu
                                root_url = "https://" + url.split('/')[2]
                                link = root_url + link if link.startswith('/') else root_url + '/' + link
                            totes.append({"titol": txt, "link": link, "font": nom})
            else:
                fails.append(f"{nom} ({res.status_code})")
        except:
            fails.append(f"{nom} (Timeout/Error)")
            
    return totes, ok, fails

# 4. IA AVANÇADA AMB GEMINI PRO (PERFIL "ADAPTABLE" I PROACTIU)
def processar_ia(dades):
    if not dades: return "No dades.", [], 0
    historial = carregar_historial()
    
    noves = [d for d in dades if d['titol'] not in historial]
    if not noves: return "Cap novetat.", [], 0

    perfil = """
    Escola Nou Patufet (I3-4t ESO). Cooperativa de treball situada a Gràcia, Barcelona.
    Som un centre compromès amb el feminisme, la coeducació i l'Economia Social i Solidària (ESS).
    
    ESTRATÈGIA DE CERCA (Sigues proactiu):
    1. Directes: Subvencions per a escoles, concerts o cooperatives.
    2. Adaptables: Convocatòries de cultura, gènere o barri on l'escola pugui presentar un projecte propi (ex: un taller d'arts, una xarxa cooperativa de barri, un pla d'igualtat).
    3. Temàtiques clau: Feminisme, català, intercooper
