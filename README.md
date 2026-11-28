# 🤖 Patu-Bot — Cercador automàtic de subvencions públiques

Bot que cada dia laborable revisa les fonts oficials de subvencions catalanes i estatals, descarta el soroll amb
un triatge d'IA i **només avisa de les convocatòries a les quals l'entitat pot optar de debò**, amb termini,
import i requisits ja extrets de la pàgina real.

Està fet per a l'**Escola Cooperativa Nou Patufet** (Barcelona), però la lògica no depèn de l'escola: el perfil
de l'entitat, les fonts i els llindars són configuració, no codi. Si ets una altra escola, cooperativa o entitat
petita que no té ningú dedicat a llegir diaris oficials cada matí, pots desplegar la teva pròpia instància
gratuïtament amb GitHub Actions (vegeu [Adaptar-ho a una altra entitat](#adaptar-ho-a-una-altra-entitat)).

## El problema que resol

Les convocatòries de subvencions es publiquen al RAISC, al CIDO, al BOE i a les webs de fundacions, amb terminis
que sovint són de dues a quatre setmanes. Una entitat petita no té ningú que ho revisi cada dia, de manera que
les perd per desconeixement, no per no encaixar-hi. Els serveis comercials de seguiment de subvencions estan
pensats per a R+D empresarial i tenen el preu corresponent. Això és una alternativa que es pot autoallotjar.

## Com decideix què és interessant

1. **Recull** (només ítems nous, mai repetits):
   - **RAISC** (Registre de subvencions de Catalunya): Generalitat, diputacions i Ajuntament de Barcelona, amb dades
     estructurades (beneficiaris, finalitat, import, termini). Es filtra *abans* de la IA: altres municipis, altres
     territoris, només persones físiques, agricultura, convocatòries ja caducades...
   - **CIDO** (Diputació de Barcelona), **BOE** (API oficial) i les webs de fundacions (la Caixa, Bofill, EduCaixa,
     Carulla, Banc Sabadell, Ajuntament BCN).
2. **Triatge amb IA** (Gemini): puntua 1-10 cada ítem pel títol i les dades. Només passen els ≥ 5.
3. **Anàlisi profunda**: es llegeix la pàgina de cada candidata i la IA en treu termini real, import, requisits i
   **elegibilitat** (Sí / Dubtós / No). Només s'avisa si l'elegibilitat no és "No" i l'**encaix és ≥ 6/10**.
4. **Sortides**: correu (HTML) ordenat per encaix, fitxa Word a Drive, i **recordatoris** quan falten ≤ 10 dies
   per a un termini.

Si alguna cosa falla (fonts caigudes, IA, Drive), **l'execució es marca com a fallida i GitHub envia un correu**.
No hi ha errors silenciosos. Els dilluns s'envia un correu de "tot OK" com a prova de vida.

## Panell web

El bot genera `docs/index.html` (totes les propostes, agrupades per organisme). Vercel el publica a
**https://subvencions-nou-patufet.vercel.app** cada cop que el bot fa commit (config a `vercel.json`).

## Fitxers

| Fitxer | Què és |
|---|---|
| `monitor_subvencions.py` | Programa principal |
| `patubot/config.py` | **Aquí s'ajusta tot**: perfil de l'entitat, llindars (`MIN_ENCAIX`...), fonts web, models |
| `patubot/fonts.py` · `ia.py` · `estat.py` · `sortida.py` | Recollida · IA · memòria · correu/Word/Drive |
| `historial_subvencions.json` | Què s'ha vist ja (per no repetir) |
| `oportunitats.json` | Oportunitats avisades, per als recordatoris |
| `ultima_execucio.json` | Resum de l'última execució (també evita que GitHub desactivi el cron) |
| `plantilla_subvencio.docx` | Plantilla de la fitxa. Marcadors: `{{titol}} {{organisme}} {{import}} {{termini}} {{resum}} {{accions}}` i opcionals `{{elegibilitat}} {{requisits}} {{adaptacio}} {{encaix}} {{link}}` |

## Configuració (Settings → Secrets and variables → Actions)

**Secrets:** `GEMINI_API_KEY`, `EMAIL_USER`, `EMAIL_PASS` (contrasenya d'aplicació de Gmail), `EMAIL_RECEIVER`
(pot ser una llista separada per comes), `GDRIVE_CREDENTIALS` (JSON del compte de servei), `SCRAPER_API_KEY`
(opcional: només per a webs que bloquegen robots, com EduCaixa).
**Variable (opcional):** `GDRIVE_FOLDER_ID`.

Cap credencial va al repositori. Si forques el projecte, substitueix també el valor per defecte de
`GDRIVE_FOLDER_ID` a `patubot/config.py` pel de la teva carpeta de Drive.

## Ajustar la sensibilitat

- Rebre més avisos: baixa `MIN_ENCAIX` (ara 6) o `MIN_PUNTUACIO_TRIATGE` (ara 5) a `patubot/config.py`.
- Rebre'n menys però millors: puja'ls.
- Canviar què interessa: edita `PERFIL_ESCOLA` a `patubot/config.py`.

## Adaptar-ho a una altra entitat

Tot el que és específic de Nou Patufet viu a `patubot/config.py`. Per desplegar la teva instància:

1. **Forca el repositori** i activa GitHub Actions.
2. **Reescriu `PERFIL_ESCOLA`** amb el teu cas. És la peça que decideix l'elegibilitat, i la que més
   determina la qualitat del resultat: hi ha d'haver la forma jurídica (cooperativa, associació, fundació,
   centre públic, empresa...), a quines convocatòries podeu optar i a quines no, el territori i els temes que
   us interessen. L'exemple actual és llarg a propòsit — com més concret, menys falsos positius.
3. **Revisa els filtres territorials i temàtics**: `FINALITATS_EXCLOSES`, `BENEFICIARIS_VALIDS` i, a
   `patubot/fonts.py`, els filtres del RAISC per municipi. Tal com està, el bot assumeix Barcelona i Catalunya.
4. **Canvia `FONTS_WEB`** per les fundacions i administracions que et toquin. El format és
   `(nom, url, necessita_javascript)`.
5. **Posa els teus secrets** (apartat anterior) i, si vols panell web, canvia `PANELL_URL` i el projecte de Vercel.
6. **Executa-ho a mà** un primer cop amb `workflow_dispatch` i la variable `ENVIA_SEMPRE=1` per veure què et surt
   abans de deixar-ho en automàtic.

Les fonts oficials que porta implementades (RAISC, CIDO, BOE) cobreixen Catalunya i l'Estat. Per a altres
comunitats autònomes caldria afegir un lector nou a `patubot/fonts.py`; les contribucions en aquesta direcció
són benvingudes.

## Desenvolupament

```bash
pip install -r requirements-dev.txt
python -m pytest -q tests
```

## Llicència

[MIT](LICENSE). Pots fer-ho servir, modificar-ho i distribuir-ho lliurement, també en projectes comercials,
mantenint l'avís de copyright. Sense cap garantia.
