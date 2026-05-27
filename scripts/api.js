/* ===================================================================
   Loader des sujets scorés depuis le backend.

   Fetch /data/sujets/latest.json (produit par
   `python -m server.cli score`) et le retourne tel quel.

   Plus d'enrichment avec un rédacteur — le briefing global est neutre.
   =================================================================== */

const SUJETS_URL = "/data/sujets/latest.json";

/**
 * Récupère les sujets scorés.
 * @returns {Promise<{ generatedAt: string, sources: object, sujets: object[] }>}
 */
export const loadSujets = async () => {
  let payload;
  try {
    const res = await fetch(SUJETS_URL, { cache: "no-store" });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status} sur ${SUJETS_URL}`);
    }
    payload = await res.json();
  } catch (err) {
    throw new ApiError(
      "Impossible de charger les sujets. Lance `python -m server.cli all` puis recharge.",
      err,
    );
  }

  if (!payload || !Array.isArray(payload.sujets)) {
    throw new ApiError("Format de réponse inattendu (champ `sujets` manquant).");
  }

  return {
    generatedAt: payload.generated_at,
    sources: payload.sources_used,
    weights: payload.weights,
    totals: payload.totals,
    sujets: payload.sujets,
    categoriesTrending: payload.categories_trending || [],
    entitiesTrending: payload.entities_trending || [],
  };
};

export class ApiError extends Error {
  constructor(message, cause) {
    super(message);
    this.name = "ApiError";
    this.cause = cause;
  }
}

/**
 * Formate une date ISO en libellé long FR (ex. "Lundi 26 mai 2026").
 * @param {string} iso
 * @returns {string}
 */
export const formatLongDate = (iso) => {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
};

/**
 * Formate une date ISO en libellé court (ex. "MAJ il y a 12 min · 08:23").
 * @param {string} iso
 * @returns {string}
 */
export const formatFreshness = (iso) => {
  if (!iso) return "Aucune donnée";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Date invalide";

  const diffMs = Date.now() - date.getTime();
  const diffMin = Math.round(diffMs / 60_000);

  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");

  let relative;
  if (diffMin < 1) relative = "à l'instant";
  else if (diffMin < 60) relative = `il y a ${diffMin} min`;
  else if (diffMin < 60 * 24) relative = `il y a ${Math.round(diffMin / 60)} h`;
  else relative = `il y a ${Math.round(diffMin / (60 * 24))} j`;

  return `MAJ ${relative} · ${hh}:${mm}`;
};
