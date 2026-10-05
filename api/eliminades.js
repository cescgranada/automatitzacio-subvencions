// Llista compartida de propostes eliminades del panell (es desa a eliminades.json al repositori).
//   GET  /api/eliminades          -> { ids: [...] }
//   POST /api/eliminades {pin,id} -> afegeix l'id a la llista (el bot la farà servir per no tornar-la a mostrar)
const { gh, pinCorrecte, configurat } = require("./_gh");

const FITXER = "eliminades.json";
const MAX_IDS = 5000;

async function llegeix() {
  const r = await gh(`/contents/${FITXER}?ref=main`);
  if (r.status === 404) return { ids: [], sha: null };
  if (!r.ok) throw new Error(`GitHub ${r.status}`);
  const j = await r.json();
  const ids = JSON.parse(Buffer.from(j.content, "base64").toString("utf-8") || "[]");
  return { ids: Array.isArray(ids) ? ids : [], sha: j.sha };
}

async function desa(ids, sha) {
  const cos = {
    message: "Panell: proposta eliminada manualment",
    content: Buffer.from(JSON.stringify(ids, null, 2) + "\n", "utf-8").toString("base64"),
    branch: "main",
  };
  if (sha) cos.sha = sha;
  return gh(`/contents/${FITXER}`, { method: "PUT", body: JSON.stringify(cos) });
}

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (!configurat()) return res.status(503).json({ error: "Servei no configurat" });
  try {
    if (req.method === "GET") return res.status(200).json({ ids: (await llegeix()).ids });
    if (req.method !== "POST") return res.status(405).json({ error: "Mètode no permès" });

    const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
    if (!pinCorrecte(body.pin)) {
      await new Promise((r) => setTimeout(r, 800));
      return res.status(401).json({ error: "Codi incorrecte" });
    }
    const id = String(body.id ?? "");
    if (!id || id.length > 400 || /[\s\u0000-\u001f]/.test(id)) return res.status(400).json({ error: "Identificador no vàlid" });

    for (let intent = 0; intent < 3; intent++) {   // si el bot o una companya hi escriu a la vegada, es reintenta
      const { ids, sha } = await llegeix();
      if (ids.includes(id)) return res.status(200).json({ ok: true, ja_hi_era: true });
      if (ids.length >= MAX_IDS) return res.status(507).json({ error: "Llista plena" });
      const r = await desa([...ids, id], sha);
      if (r.ok) return res.status(200).json({ ok: true });
      if (r.status !== 409 && r.status !== 422) {
        return res.status(502).json({ error: `GitHub ha respost ${r.status}`, detall: r.status === 403 || r.status === 404 ? "El token necessita el permís Contents: Read and write" : undefined });
      }
    }
    return res.status(409).json({ error: "Conflicte, torna-ho a provar" });
  } catch (e) {
    return res.status(500).json({ error: String(e.message || e) });
  }
};
