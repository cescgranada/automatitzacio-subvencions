# 📢 Automatització de Subvencions (BOE, DOGC, BOPB)

Aquest projecte llegeix diàriament els diaris oficials, filtra les subvencions amb IA (Gemini) i envia un resum per correu.

## 🚀 Com fer-ho servir (Guia ràpida)
1. Clica el botó verd **"Use this template"** per crear el teu propi repositori.
2. Ves a **Settings > Secrets and variables > Actions** i afegeix aquests 4 secrets:
   - `GEMINI_API_KEY`: La teva clau de Google AI Studio.
   - `EMAIL_USER`: El teu correu de Gmail.
   - `EMAIL_PASS`: La "Contrasenya d'aplicació" de 16 lletres de Google.
   - `EMAIL_RECEIVER`: On vols rebre el resum.
3. Edita el fitxer `monitor_subvencions.py` i canvia la variable `perfil` amb la descripció de la teva entitat.
4. Ves a la pestanya **Actions** i clica a **"Enable Actions"** per activar el rellotge diari.
