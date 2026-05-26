/* ===================================================================
   Pool de rédacteurs mock (en attendant le byline mapper Phase 1)
   ===================================================================

   Le scoring backend (server/scoring/) ne produit pas encore d'auteur
   recommandé — cela viendra avec l'import GSC + byline scraping.
   En attendant, on attribue un rédacteur du pool en fonction de la
   catégorie MSN du sujet (cf assignReporterByTheme).
*/

export const reporters = {
  sm: {
    id: "sm",
    initials: "SM",
    name: "Sophie Martin",
    theme: "People premium",
    themeScore: 92,
    discoverArticles30d: 14,
    avatarBg: "linear-gradient(135deg, #5B3A6E, #1E2236)",
  },
  ad: {
    id: "ad",
    initials: "AD",
    name: "Antoine Dubois",
    theme: "Investigation société",
    themeScore: 84,
    discoverArticles30d: 9,
    avatarBg: "linear-gradient(135deg, #2C4860, #1E2236)",
  },
  ml: {
    id: "ml",
    initials: "ML",
    name: "Marie Lefebvre",
    theme: "Royauté · monarchies",
    themeScore: 88,
    discoverArticles30d: 11,
    avatarBg: "linear-gradient(135deg, #6B4E2A, #1E2236)",
  },
  jp: {
    id: "jp",
    initials: "JP",
    name: "Julien Petit",
    theme: "Sport",
    themeScore: 79,
    discoverArticles30d: 8,
    avatarBg: "linear-gradient(135deg, #2A5C3A, #1E2236)",
  },
  cr: {
    id: "cr",
    initials: "CR",
    name: "Camille Roux",
    theme: "Culture · cinéma",
    themeScore: 81,
    discoverArticles30d: 10,
    avatarBg: "linear-gradient(135deg, #6E2A4E, #1E2236)",
  },
  tb: {
    id: "tb",
    initials: "TB",
    name: "Thomas Bernard",
    theme: "Politique",
    themeScore: 76,
    discoverArticles30d: 6,
    avatarBg: "linear-gradient(135deg, #4E2A3A, #1E2236)",
  },
  lm: {
    id: "lm",
    initials: "LM",
    name: "Léa Moreau",
    theme: "International",
    themeScore: 71,
    discoverArticles30d: 5,
    avatarBg: "linear-gradient(135deg, #2A3D5C, #1E2236)",
  },
  ev: {
    id: "ev",
    initials: "ÉV",
    name: "Élise Vidal",
    theme: "Breaking / faits divers",
    themeScore: 83,
    discoverArticles30d: 12,
    avatarBg: "linear-gradient(135deg, #5C2A2A, #1E2236)",
  },
};

/* -------------------------------------------------------------------
   Mapping catégorie MSN → rédacteur recommandé + alternatives.

   Les catégories MSN sont en français ; on matche en lowercase contains
   pour rester tolérant aux variations (divertissement, divertissements,
   actu, actualité, etc.).
   ------------------------------------------------------------------- */

const THEME_MAP = [
  { match: ["divertissement", "people", "celebrites", "celeb"], primary: "sm", alts: ["cr", "ev"] },
  { match: ["royaute", "monarchie", "royal"], primary: "ml", alts: ["sm", "ev"] },
  { match: ["sport"], primary: "jp", alts: ["ad"] },
  { match: ["culture", "cinema", "musique", "livre"], primary: "cr", alts: ["sm"] },
  { match: ["politique", "presidentielle", "gouvernement"], primary: "tb", alts: ["ad"] },
  { match: ["international", "monde", "etranger"], primary: "lm", alts: ["ad", "ev"] },
  { match: ["actualite", "societe", "faits", "fait-divers", "justice"], primary: "ev", alts: ["ad", "lm"] },
  { match: ["lifestyle", "vie", "bien-etre", "sante"], primary: "sm", alts: ["cr"] },
  { match: ["economie", "finance", "argent"], primary: "ad", alts: ["tb"] },
];

const DEFAULT_REPORTER = "ev"; // Breaking par défaut — couvre tout ce qui n'est pas typé

/** Assigne un rédacteur principal + 2 alternatives selon la catégorie. */
export const assignReporterByTheme = (theme) => {
  const t = String(theme || "").toLowerCase();
  const found = THEME_MAP.find(({ match }) => match.some((kw) => t.includes(kw)));
  const primaryId = found?.primary ?? DEFAULT_REPORTER;
  const altIds = (found?.alts ?? []).filter((id) => id !== primaryId);

  return {
    primary: reporters[primaryId],
    alts: altIds.map((id) => reporters[id]).filter(Boolean),
  };
};

/* -------------------------------------------------------------------
   Utilitaires de tier (alignés avec le backend server/scoring/score.py)
   ------------------------------------------------------------------- */

// Doit rester aligné avec server/scoring/score.py / tier_from_score()
export const tierFromScore = (score) => {
  if (score >= 50) return "high";
  if (score >= 30) return "medium";
  return "low";
};

export const tierLabel = {
  high: "Signal fort",
  medium: "Signal moyen",
  low: "Signal faible",
};

/* -------------------------------------------------------------------
   Données rédacteur "moi" pour la vue reporter.html (mock conservé).
   Sera remplacé quand le byline mapper produira data/byline/me.json.
   ------------------------------------------------------------------- */

export const reporterMe = reporters.sm;

export const myTopics = [
  {
    id: "m01",
    score: 92,
    theme: "People",
    title: "Brigitte Macron : la photo d'anniversaire exclusive de l'Élysée fuite avant l'heure",
    why: {
      lead: "Tu es notre top performer People premium",
      stats: "14 articles Discover sur 30 jours · CTR 8.4% · 6 dans le top 10 mensuel",
    },
    signals: [
      { source: "trends", label: "trends", value: "+412%" },
      { source: "x", label: "x", value: "8.4k t/h" },
      { source: "news", label: "news", value: "78 art." },
    ],
    refs: [
      "Paris Match · 12 mai — Les 73 ans de Brigitte : ce que prépare l'Élysée",
      "PM archive — Anniversaires présidentiels, 10 ans de couverture",
    ],
    deadline: "Livraison avant 11 h",
    state: "doing",
  },
  {
    id: "m02",
    score: 74,
    theme: "People · cinéma",
    title: "Léa Seydoux à Cannes : ce que sa robe noire raconte de son année",
    why: {
      lead: "Sujet à la croisée de People et Culture",
      stats: "Tu performes mieux que Camille sur les angles People-cinéma (+18% CTR)",
    },
    signals: [
      { source: "trends", label: "trends", value: "+340%" },
      { source: "x", label: "x", value: "12.1k t/h" },
    ],
    refs: [
      "Paris Match · 14 mai — Cannes 2026, le programme du tapis rouge",
    ],
    deadline: "Livraison avant 14 h",
    state: "todo",
  },
  {
    id: "m03",
    score: 61,
    theme: "Royauté · backup",
    title: "Charlene de Monaco : préparer un papier d'angle si retour confirmé",
    why: {
      lead: "Backup sur le sujet Royauté de Marie Lefebvre",
      stats: "Bon historique sur les sujets monégasques (3 papiers en top 30 cette année)",
    },
    signals: [
      { source: "trends", label: "trends", value: "+218%" },
      { source: "wiki", label: "wiki", value: "22k/h" },
    ],
    refs: [],
    deadline: "Au cas où — pas de deadline ferme",
    state: "todo",
  },
];
