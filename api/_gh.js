// Utilitats compartides per a les funcions de /api (el prefix "_" evita que Vercel les publiqui com a ruta).
const crypto = require("crypto");

const REPO = "cescgranada/automatitzacio-subvencions";

const gh = (path, opts = {}) =>
  fetch(`https://api.github.com/repos/${REPO}${path}`, {
    ...opts,
    headers: {
      Authorization: `Bearer ${(process.env.GITHUB_DISPATCH_TOKEN || "").trim()}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "patubot-panell",
      ...(opts.headers || {}),
    },
  });

const hash = (s) => crypto.createHash("sha256").update(String(s)).digest();

const pinCorrecte = (pin) =>
  crypto.timingSafeEqual(hash(pin ?? ""), hash((process.env.ACCES_PIN || "").trim()));

const configurat = () => !!(process.env.GITHUB_DISPATCH_TOKEN && process.env.ACCES_PIN);

module.exports = { gh, pinCorrecte, configurat, REPO };
