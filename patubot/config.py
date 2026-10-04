"""Configuració del Patu-Bot: tot el que es pot ajustar sense tocar la lògica."""
import os

GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID") or "14Fgh_2rU43gsiXhaTGE-vAFGEqSoXYfW"  # millor: definir-lo com a variable/secret
HISTORIAL_FILE = "historial_subvencions.json"
OPORTUNITATS_FILE = "oportunitats.json"
ESTAT_FILE = "ultima_execucio.json"

# Models de Gemini, per ordre de preferència (si un està retirat, prova el següent)
GEMINI_MODELS = [m.strip() for m in os.getenv("GEMINI_MODELS") or "gemini-2.5-flash,gemini-2.0-flash".split(",") if m.strip()]

# --- Finestres de temps ---------------------------------------------------
DIES_FINESTRA = 75        # convocatòries publicades en els últims N dies (RAISC/CIDO)
DIES_BOE = 4              # dies de BOE a revisar (cobreix el cap de setmana)
DIES_RECORDATORI = 10     # recordar oportunitats amb termini d'aquí a ≤ N dies
DIES_ENTRE_RECORDATORIS = 4

# --- Qualitat de les oportunitats ----------------------------------------
MIN_PUNTUACIO_TRIATGE = 5   # fase 1 (títols): descarta per sota d'aquest valor
MAX_CANDIDATES = 25         # màxim de pàgines que es llegeixen a fons cada dia
MIN_ENCAIX = 6              # fase 2 (pàgina real): només s'avisa per sobre d'aquest valor
BATCH_TRIATGE = 40
MAX_CHARS_PAGINA = 12000

# --- Filtres deterministes sobre el RAISC --------------------------------
FINALITATS_EXCLOSES = (
    "agricultura", "industria i energia", "subvencions al transport",
    "acces a l'habitatge", "comerc, turisme",
)
BENEFICIARIS_VALIDS = ("juridiques", "pyme", "gran empresa")  # descarta "només persones físiques"

# --- Webs que cal rascar (no tenen API) ----------------------------------
FONTS_WEB = [
    ("Fundació la Caixa", "https://fundacionlacaixa.org/ca/convocatories-socials", False),
    ("Fundació Bofill", "https://fundaciobofill.cat/crides", True),
    ("EduCaixa", "https://educaixa.org/ca/convocatories", True),
    ("Fundació Carulla", "https://fundaciocarulla.cat/", True),
    ("Fundació Banc Sabadell", "https://www.fundacionbancosabadell.com/convocatorias/", False),
    ("Ajuntament BCN (subvencions)", "https://ajuntament.barcelona.cat/ca/informacio-administrativa/subvencions", False),
]
# tercer valor: la pàgina necessita JavaScript (només s'usa amb ScrapingBee)

LINKS_IGNORATS = (
    "translate.google", "youtube.com", "facebook.com", "twitter.com", "instagram.com",
    "linkedin.com", "reset=1", "javascript:", "mailto:", "/cookies", "/privacitat",
    "/avis-legal", "aviso-legal", "politica-de",
)

PERFIL_ESCOLA = """
Escola Nou Patufet (I3-4t ESO). Cooperativa de treball situada a Gràcia, Barcelona.
Centre compromès amb el feminisme, la coeducació i l'Economia Social i Solidària (ESS).

QUÈ INTERESSA:
1. Directes: ajuts per a escoles/centres educatius, cooperatives de treball o entitats sense ànim de lucre.
2. Adaptables: cultura, gènere, barri, sostenibilitat o innovació on l'escola pugui presentar un projecte propi
   (taller d'arts, xarxa cooperativa de barri, pla d'igualtat, transició ecològica, activitats extraescolars...).
3. Temàtiques clau: feminisme i coeducació, llengua catalana, intercooperació i ESS, arts escèniques i cultura,
   sostenibilitat i ecologia, inclusió i diversitat funcional, innovació pedagògica, millora d'espais/infraestructura
   del centre, famílies i vulnerabilitat socioeconòmica (projectes de centre, no beques individuals).

QUÈ NO INTERESSA:
agricultura/ramaderia, recerca universitària, infraestructures viàries, ajuts només per a grans empreses mercantils,
beques individuals per a alumnes (menjador/transport/material), esport d'elit, convocatòries d'altres municipis
que no siguin Barcelona, ajuts només per a persones físiques.
"""
