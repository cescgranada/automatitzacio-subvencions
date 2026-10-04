// Funció de Vercel: permet llançar la lectura del Patu-Bot des del panell.
//   GET  /api/lectura  -> { en_curs, ultima, conclusio, url }   (només lectura)
//   POST /api/lectura  -> {pin}  valida el codi i dispara el workflow de GitHub Actions
// Variables d'entorn (Vercel): GITHUB_DISPATCH_TOKEN (permís Actions: read/write només en aquest repo) i ACCES_PIN.
const crypto = require("crypto");

const REPO = "cescgranada/automatitzacio-subvencions";
const WORKFLOW = "cron_diari.yml";
const ACTIUS = ["queued", "in_progress", "waiting", "requested", "pending"];

const gh = (path, opts = {}) =>
  fetch(`https://api.github.com/repos/${REPO}${path}`, {
    ...opts,
    headers: {
      Authorization: `Bearer ${process.env.GITHUB_DISPATCH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "patubot-panell",
      ...(opts.headers || {}),
    },
  });

async function estat() {
  const r = await gh(`/actions/workflows/${WORKFLOW}/runs?per_page=1`);
  if (!r.ok) throw new Error(`GitHub ${r.status}`);
  const run = (await r.json()).workflow_runs?.[0];
  return {
    en_curs: !!run && ACTIUS.includes(run.status),
    ultima: run?.updated_at || null,
    conclusio: run?.conclusion || null,
    url: run?.html_url || null,
  };
}

const hash = (s) => crypto.createHash("sha256").update(String(s)).digest();

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (!process.env.GITHUB_DISPATCH_TOKEN || !process.env.ACCES_PIN) {
    return res.status(503).json({ error: "Servei no configurat" });
  }
  try {
    if (req.method === "GET") return res.status(200).json(await estat());
    if (req.method !== "POST") return res.status(405).json({ error: "Mètode no permès" });

    const body = typeof req.body === "string" ? JSON.parse(req.body || "{}") : req.body || {};
    if (!crypto.timingSafeEqual(hash(body.pin ?? ""), hash(process.env.ACCES_PIN))) {
      await new Promise((r) => setTimeout(r, 800)); // frena els intents de força bruta
      return res.status(401).json({ error: "Codi incorrecte" });
    }
    if ((await estat()).en_curs) return res.status(409).json({ error: "Ja hi ha una lectura en curs" });

    const r = await gh(`/actions/workflows/${WORKFLOW}/dispatches`, {
      method: "POST",
      body: JSON.stringify({ ref: "main" }),
    });
    if (r.status !== 204) return res.status(502).json({ error: `GitHub ha respost ${r.status}` });
    return res.status(202).json({ ok: true });
  } catch (e) {
    return res.status(500).json({ error: String(e.message || e) });
  }
};
