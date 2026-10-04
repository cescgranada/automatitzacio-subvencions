# 🤖 Patu-Bot v3 — Cercador de subvencions per a l'Escola Nou Patufet

Cada dia laborable revisa fonts oficials, descarta el soroll i **només t'avisa de les convocatòries a les quals
l'escola pot optar de debò**, amb termini, import i requisits ja extrets de la pàgina real.

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

Si alguna cosa falla (fonts caigudes, IA, Drive), **l'execució es marca com a fallida i GitHub t'envia un correu**.
Ja no hi ha errors silenciosos. Els dilluns s'envia un correu de "tot OK" com a prova de vida.

## Panell web

El bot genera `docs/index.html` (totes les propostes, agrupades per organisme). Vercel el publica a
**https://subvencions-nou-patufet.vercel.app** cada cop que el bot fa commit (config a `vercel.json`).

## Fitxers

| Fitxer | Què és |
|---|---|
| `monitor_subvencions.py` | Programa principal |
| `patubot/config.py` | **Aquí s'ajusta tot**: perfil de l'escola, llindars (`MIN_ENCAIX`...), fonts web, models |
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

## Ajustar la sensibilitat

- Rebre més avisos: baixa `MIN_ENCAIX` (ara 6) o `MIN_PUNTUACIO_TRIATGE` (ara 5) a `patubot/config.py`.
- Rebre'n menys però millors: puja'ls.
- Canviar què interessa: edita `PERFIL_ESCOLA` a `patubot/config.py`.

## Desenvolupament

```bash
pip install -r requirements-dev.txt
python -m pytest -q tests
```
