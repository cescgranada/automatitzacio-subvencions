"""Configuració del Patu-Bot: tot el que es pot ajustar sense tocar la lògica."""
import os

GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID") or "14Fgh_2rU43gsiXhaTGE-vAFGEqSoXYfW"  # millor: definir-lo com a variable/secret
HISTORIAL_FILE = "historial_subvencions.json"
OPORTUNITATS_FILE = "oportunitats.json"
ESTAT_FILE = "ultima_execucio.json"
PROPOSTES_FILE = "propostes.json"
ELIMINADES_FILE = "eliminades.json"   # ids eliminats des del panell (els escriu la funció api/eliminades)
PANELL_FILE = "docs/index.html"
PANELL_URL = "https://subvencions-nou-patufet.vercel.app/"

# Fonts que el bot no pot llegir sol (bloquegen robots): el panell les mostra com a revisió manual
FONTS_MANUALS = [
    ("EduCaixa", "https://educaixa.org/ca/convocatories"),
    ("Fundació Carulla", "https://fundaciocarulla.cat/"),
]

# Models de Gemini, per ordre de preferència (si un està retirat, prova el següent)
GEMINI_MODELS = [m.strip() for m in os.getenv("GEMINI_MODELS") or "gemini-3.8-flash,gemini-2.5-flash".split(",") if m.strip()]

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
    ("Fundació Banc Sabadell", "https://www.fundacionbancosabadell.com/convocatorias/", False),
    ("Ajuntament BCN (subvencions)", "https://ajuntament.barcelona.cat/ca/informacio-administrativa/subvencions", False),
    ("Coòpolis (ESS Barcelona)", "https://www.bcn.coop/category/noticies/", False),
]
# tercer valor: la pàgina necessita JavaScript (només s'usa amb ScrapingBee)

LINKS_IGNORATS = (
    "translate.google", "youtube.com", "facebook.com", "twitter.com", "instagram.com",
    "linkedin.com", "reset=1", "javascript:", "mailto:", "/cookies", "/privacitat",
    "/avis-legal", "aviso-legal", "politica-de",
)

PERFIL_ESCOLA = """
Escola Nou Patufet (I3-4t ESO, ~escola cooperativa al cor de Gràcia), a la Vila de Gràcia (Barcelona).

FORMA JURÍDICA I ELEGIBILITAT (clau per decidir "Sí / Dubtós / No"):
- Som una SCCL: cooperativa de TREBALL ASSOCIAT des de l'1/09/2015 (les sòcies són docents i personal d'administració
  i serveis; va néixer del tancament de l'Escola Patufet). Opera com a ESCOLA CONCERTADA: titularitat privada
  cooperativa, finançada amb concert del Departament d'Educació. NO som un centre públic.
- NO som una entitat sense ànim de lucre (ni associació ni fundació): som una cooperativa que desenvolupa activitat
  econòmica. Ens correspon la categoria de PYME / persona jurídica que desenvolupa activitat econòmica, i la d'entitat
  de l'Economia Social i Solidària (ESS).
- SÍ podem optar a: convocatòries per a cooperatives o ESS; per a PYME o empreses; per a "centres educatius" o
  "centres sostinguts amb fons públics / concertats" quan no exigeixin titularitat pública; i per a "persones
  jurídiques" sense restricció a entitats sense ànim de lucre.
- NO podem optar a: convocatòries només per a entitats SENSE ÀNIM DE LUCRE (associacions, fundacions), només per a
  centres públics, ajuntaments/administracions o persones físiques, ni les que exclouen explícitament cooperatives.
  Si el text és ambigu sobre si una cooperativa hi encaixa, marca "Dubtós" i explica-ho.
- Territori: Barcelona ciutat i Gràcia (especialment rellevants), Catalunya, Estat i Europa.

TRETS DEL PROJECTE (per valorar l'encaix temàtic):
Feminisme i coeducació, educació en drets, Economia Social i Solidària i intercooperació (EscolesCoop, cooperativa
d'alumnes AlumnesCoop, "Empreses amb propòsit"), arrelament al territori/barri (Vila del llibre, Amor-estima-passió pel
territori), sostenibilitat (Escoles +sostenibles), innovació pedagògica (Educació 360, Escola Nova 21, aprenentatge
basat en projectes, estratègia digital de centre), educació emocional i mindfulness, cultura i arts (Escola de rock,
Fem cinema, Drama club), llengua i lectura (Pla d'impuls a la lectura), anglès, esport i natació, Diploma Dual i
Programa Actuem a l'ESO, extraescolars i migdies educatius oberts al barri, casal d'estiu i Casal Jove, centre formador
de professorat, projectes amb UNICEF Catalunya i Fundació Tr@ms.

QUÈ INTERESSA:
1. Directes: ajuts per a escoles/centres educatius (inclosos concertats), cooperatives de treball, ESS.
2. Adaptables: cultura, gènere, barri, sostenibilitat, innovació o digitalització on l'escola pugui presentar un
   projecte propi (taller d'arts, xarxa cooperativa de barri, pla d'igualtat, transició ecològica, extraescolars...).
3. També ajuts a empreses/PYME útils per a una cooperativa: digitalització, ocupació i formació de l'equip, eficiència
   energètica, millora d'espais, intercooperació, plans d'igualtat.

QUÈ NO INTERESSA:
agricultura/ramaderia, recerca universitària, infraestructures viàries, ajuts només per a grans empreses mercantils,
beques individuals per a alumnes (menjador/transport/material), esport d'elit, convocatòries d'altres municipis que
no siguin Barcelona, ajuts només per a persones físiques o només per a entitats sense ànim de lucre.
"""
