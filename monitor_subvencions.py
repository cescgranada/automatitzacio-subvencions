import requests
import os
import smtplib
import io
import json
import time
import random
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from lxml import etree
from datetime import datetime
from google import genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
# Corregit: eliminat l'error de MediaIoBaseUpload
from googleapiclient.http import MediaIoBaseUpload
from docx import Document

# 1. CONFIGURACIÓ
API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=API_KEY)
GDRIVE_FOLDER_ID = "14Fgh_2rU43gsiXhaTGE-vAFGEqSoXYfW"
HISTORIAL_FILE = "historial_subvencions.json"

# Llista de User-Agents per rotar i semblar humà
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0'
]

# 2. GESTIÓ DE MEMÒRIA
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

# 3. CERCA DE FONTS ROBUSTA
def cercar_fonts():
    session = requests.Session()
    totes = []; ok_list = []; fail_list = []
    
    # Definició de fonts amb mètodes alternatius
    fonts_config = [
        {
            "nom": "DOGC Subvencions",
            "url": "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_ajuts_subvencions_i_beques/index.rss",
            "tipus": "rss"
        },
        {
            "nom": "DOGC Europa",
            "url": "https://dogc.gencat.cat/ca/pdogc_canals_rss/pdogc_subvencions_internacionals/index.rss",
            "tipus": "rss"
        },
        {
            "nom": "BOPB Barcelona",
            "url": "https://bop.diba.cat/rss.asp?seccio=4.2",
            "tipus": "rss"
        },
        {
            "nom": "BOE Estat",
            "url": f"https://www.boe.es/diario_boe/xml.php?id=BOE-S-{datetime.now().strftime('%Y%m%d')}",
            "tipus": "xml_boe"
        },
        {
            "nom": "Fundació la Caixa",
            "url": "https://fundacionlacaixa.org/ca/convocatories-socials-presentacio-projectes",
            "tipus": "html"
        },
        {
            "nom": "Fundació Bofill",
            "url": "https://fundaciobofill.cat/crides",
            "tipus": "html"
        },
        {
            "nom": "EduCaixa",
            "url": "https://educaixa.org/ca/convocatories",
            "tipus": "html"
        }
    ]

    for f in fonts_config:
        try:
            # Pausa aleatòria incremental per no semblar un bot
            time.sleep(random.uniform(3, 7))
            
            headers = {
                'User-Agent': random.choice(USER_AGENTS),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'ca,es;q=0.9,en;q=0.8',
                'Referer': 'https://www.google.com/search?q=subvencions+educacio+catalunya',
                'Connection': 'keep-alive'
            }

            res = session.get(f['url'], timeout=30, headers=headers, allow_redirects=True)
            
            if res.status_code == 200:
                ok_list.append(f['nom'])
                contingut = res.content
                
                if f['tipus'] in ["rss", "xml_boe"]:
                    parser = etree.XMLParser(recover=True, encoding='utf-8')
                    root = etree.fromstring(contingut, parser=parser)
                    items = root.xpath("//item") or root.xpath("//anuncio")
                    for i in items[:15]:
                        t = i.findtext('title') or i.findtext('titulo') or "Sense títol"
                        l = i.findtext('link') or (("https://www.boe.es" + i.findtext('url_pdf')) if i.findtext('url_pdf') else f['url'])
                        totes.append({"titol": t, "link": l, "font": f['nom']})
                
                else: # HTML Scraping
                    soup = BeautifulSoup(contingut, 'html.parser')
                    # Busquem links i títols de forma genèrica i robusta
                    for link in soup.find_all(['h2', 'h3', 'a'], limit=20):
                        text = link.get_text().strip()
                        href = link.get('href') if link.name == 'a' else None
                        if len(text) > 25: # Filtre per evitar soroll
                            totes.append({
                                "titol": text, 
                                "link": href if href and href.startswith('http') else f['url'], 
                                "font": f['nom'],
                                "contingut": text
                            })
            else:
                fail_list.append(f"{f['nom']} (Error {res.status_code})")
        
        except Exception as e:
            fail_list.append(f"{f['nom']} (Error Connexió)")
            
    return totes, ok_list, fail_list

# 4. PROCESSAMENT IA
def processar_ia(dades):
    if not dades: return "Cap dada nova.", [], 0
    historial = carregar_historial()
    noves = [d for d in dades if d['titol'] not in historial]
    
    if not noves: return "Sense novetats.", [], 0

    perfil = """Escola Nou Patufet (I3-4t ESO). Cooperativa a Gràcia. 
    Focus: Concerts, ESS, Convenis, Licitacions, Erasmus+, Equitat, Laboral."""
    
    prompt = f"Analitza: {json.dumps(noves)}. Context: {perfil}. Respon JSON pur [] amb: titol, prioritat, organisme, import, termini, resum, accions, link_pdf."
    
    try:
        response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
        net = response.text.replace("```json", "").replace("```", "").strip()
        interessants = json.loads(net)
    except: return "Error IA.", [], len(noves)

    for s in interessants:
        try:
            nom_net = s['titol'][:45].replace("/", "-").strip()
            w_buf = crear_fitxa_word(s)
            if w_buf:
                pujar_a_drive(w_buf, f"PRIO{s['prioritat']}_{nom_net}.docx", 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        except: continue
        
    return f"Trobades {len(interessants)} oportunitats.", interessants, len(noves)

# 5. DRIVE I WORD
def crear_fitxa_word(dades):
    try:
        doc = Document('plantilla_subvencio.docx')
        for p in doc.paragraphs:
            for clau in ['titol', 'organisme', 'import', 'termini', 'resum', 'accions']:
                placeholder = f"{{{{{clau}}}}}"
                if placeholder in p.text:
                    p.text = p.text.replace(placeholder, str(dades.get(clau, 'No indicat')))
        buf = io.BytesIO(); doc.save(buf); buf.seek(0)
        return buf
    except: return None

def pujar_a_drive(contingut, nom, mimetype):
    try:
        creds = service_account.Credentials.from_service_account_info(json.loads(os.getenv("GDRIVE_CREDENTIALS")))
        service = build('drive', 'v3', credentials=creds)
        media = MediaIoBaseUpload(io.BytesIO(contingut.read()) if hasattr(contingut, 'read') else io.BytesIO(contingut), mimetype=mimetype)
        service.files().create(body={'name': nom, 'parents': [GDRIVE_FOLDER_ID]}, media_body=media).execute()
    except: pass

# 6. MAIL
def enviar_mail(text):
    u, p, r = os.getenv("EMAIL_USER"), os.getenv("EMAIL_PASS"), os.getenv("EMAIL_RECEIVER")
    msg = MIMEText(text, 'plain', 'utf-8')
    msg['Subject'] = f"🚀 Patu-bot Report: {datetime.now().strftime('%d/%m/%Y')}"
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(u, p); server.sendmail(u, r, msg.as_string())
    except: pass

# 7. MAIN
def main():
    print("Iniciant Patu-bot Ultra-Robust v2026...")
    dades, ok, fails = cercar_fonts()
    resum, interessants, n_analitzades = processar_ia(dades)
    guardar_historial([d['titol'] for d in dades])
    
    informe = f"--- INFORME DIARI PATU-BOT ---\n\n✅ OK ({len(ok)}): {', '.join(ok)}\n"
    if fails: informe += f"⚠️ ERROR ({len(fails)}): {', '.join(fails)}\n"
    informe += f"\nOportunitats: {len(interessants)}\nAnalitzades: {n_analitzades}\n\nSalutacions!"
    enviar_mail(informe)

if __name__ == "__main__":
    main()
