/* ===================================================================
   Mock data — Paris Match newsroom, 18 mai 2026
   =================================================================== */

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

const r = (id) => reporters[id];

/* ----- Sujets du jour ----- */

export const sujets = [
  {
    id: "s01",
    rank: 1,
    title: "Brigitte Macron : la photo d'anniversaire exclusive de l'Élysée fuite avant l'heure",
    theme: "People",
    score: 92,
    rationale:
      "Vélocité explosive sur les 90 dernières minutes — trois sources de signal s'alignent. Sujet « People premium » à fort potentiel Discover, fenêtre courte.",
    signals: [
      { source: "trends", label: "trends", value: "+412%" },
      { source: "wiki", label: "wiki", value: "31k/h" },
      { source: "x", label: "x", value: "8.4k t/h" },
      { source: "news", label: "news", value: "78 art." },
    ],
    sources: [
      { name: "Google Trends", value: "+412%", fill: 92 },
      { name: "Wikimedia", value: "31 200 vues/h", fill: 84 },
      { name: "X velocity", value: "8 400 t/h", fill: 88 },
      { name: "Google News", value: "78 articles", fill: 76 },
      { name: "GSC historique", value: "Top 5% catégorie", fill: 70 },
    ],
    reporter: r("sm"),
    reporterRationale: {
      lead: "Top performer People premium sur 30 jours",
      stats: "14 articles Discover · CTR 8.4% · 6 dans le top 10 mensuel",
    },
    altReporters: [r("ev"), r("ml")],
    refs: [
      "Paris Match · 12 mai 2026 — Les 73 ans de Brigitte : ce que prépare l'Élysée",
      "Le Parisien · 17 mai — Anniversaire présidentiel à Brégançon ?",
    ],
  },
  {
    id: "s02",
    rank: 2,
    title: "Charlene de Monaco fait son grand retour officiel à Monte-Carlo",
    theme: "Royauté",
    score: 88,
    rationale:
      "Pic de recherche soutenu depuis 24 h, alignement Trends + Wikipedia. Sujet récurrent à fort historique GSC pour ce titre.",
    signals: [
      { source: "trends", label: "trends", value: "+218%" },
      { source: "wiki", label: "wiki", value: "22k/h" },
      { source: "news", label: "news", value: "54 art." },
      { source: "gsc", label: "gsc", value: "top 5%" },
    ],
    sources: [
      { name: "Google Trends", value: "+218%", fill: 78 },
      { name: "Wikimedia", value: "22 100 vues/h", fill: 72 },
      { name: "X velocity", value: "3 200 t/h", fill: 62 },
      { name: "Google News", value: "54 articles", fill: 68 },
      { name: "GSC historique", value: "Top 5% catégorie", fill: 90 },
    ],
    reporter: r("ml"),
    reporterRationale: {
      lead: "Plume de référence sur la famille princière",
      stats: "11 articles Discover · 4 dans le top mensuel · 88 score thématique",
    },
    altReporters: [r("sm"), r("ev")],
    refs: [
      "Paris Match · 9 mai 2026 — Charlene, dix ans après le mariage qui a tout changé",
      "Hello! Magazine · 16 mai — Princess Charlene's official return scheduled",
    ],
  },
  {
    id: "s03",
    rank: 3,
    title: "Cannes 2026 : la robe noire de Léa Seydoux affole le tapis rouge",
    theme: "Culture",
    score: 81,
    rationale:
      "Pic court (≤ 12 h) mais très intense. Fenêtre de couverture courte — décision à prendre avant 10 h.",
    signals: [
      { source: "trends", label: "trends", value: "+340%" },
      { source: "x", label: "x", value: "12.1k t/h" },
      { source: "news", label: "news", value: "92 art." },
    ],
    sources: [
      { name: "Google Trends", value: "+340%", fill: 88 },
      { name: "Wikimedia", value: "9 400 vues/h", fill: 44 },
      { name: "X velocity", value: "12 100 t/h", fill: 92 },
      { name: "Google News", value: "92 articles", fill: 82 },
      { name: "GSC historique", value: "Top 12% catégorie", fill: 60 },
    ],
    reporter: r("cr"),
    reporterRationale: {
      lead: "Couvre Cannes pour Paris Match depuis 4 éditions",
      stats: "10 articles Discover sur le festival · 81 score Culture",
    },
    altReporters: [r("sm"), r("ad")],
    refs: [
      "Paris Match · 14 mai — Cannes 2026 : ce qu'il faut voir cette année",
    ],
  },
  {
    id: "s04",
    rank: 4,
    title: "Mort du compositeur Vladimir Cosma : hommages unanimes du cinéma français",
    theme: "Culture · obit",
    score: 76,
    rationale:
      "Sujet à forte rémanence : pic court mais signaux longue traîne attendus. Plusieurs angles disponibles (biographie, hommages, héritage).",
    signals: [
      { source: "trends", label: "trends", value: "+1240%" },
      { source: "wiki", label: "wiki", value: "48k/h" },
      { source: "news", label: "news", value: "210 art." },
    ],
    sources: [
      { name: "Google Trends", value: "+1240%", fill: 96 },
      { name: "Wikimedia", value: "48 000 vues/h", fill: 90 },
      { name: "X velocity", value: "4 100 t/h", fill: 56 },
      { name: "Google News", value: "210 articles", fill: 88 },
      { name: "GSC historique", value: "Faible volume", fill: 22 },
    ],
    reporter: r("cr"),
    reporterRationale: {
      lead: "Plume Culture · meilleure perf sur les hommages",
      stats: "3 nécrologies en top 10 Discover sur 12 mois",
    },
    altReporters: [r("ad"), r("tb")],
    refs: [
      "Le Monde · 18 mai 06:45 — Vladimir Cosma est mort à 86 ans",
    ],
  },
  {
    id: "s05",
    rank: 5,
    title: "Investigation : ce que cache le rapport de la commission Cazeneuve",
    theme: "Société",
    score: 67,
    rationale:
      "Signal qualitatif fort sur Google News + GSC. Pas un sujet de pic, mais un sujet à profondeur — bien rentabilisé sur le long terme.",
    signals: [
      { source: "news", label: "news", value: "44 art." },
      { source: "gsc", label: "gsc", value: "top 8%" },
      { source: "trends", label: "trends", value: "+58%" },
    ],
    sources: [
      { name: "Google Trends", value: "+58%", fill: 35 },
      { name: "Wikimedia", value: "1 200 vues/h", fill: 12 },
      { name: "X velocity", value: "850 t/h", fill: 22 },
      { name: "Google News", value: "44 articles", fill: 60 },
      { name: "GSC historique", value: "Top 8%", fill: 82 },
    ],
    reporter: r("ad"),
    reporterRationale: {
      lead: "Référent Investigation société",
      stats: "9 enquêtes Discover · 84 score thématique",
    },
    altReporters: [r("tb"), r("ev")],
    refs: [
      "Mediapart · 17 mai — Le pavé de 312 pages que personne ne lit",
    ],
  },
  {
    id: "s06",
    rank: 6,
    title: "Roland-Garros : la révélation française qui peut faire trembler le tableau",
    theme: "Sport",
    score: 58,
    rationale:
      "Signal modéré, mais alignement Sport sur la semaine du tournoi. Bon ratio effort / performance pour l'auteur historique.",
    signals: [
      { source: "trends", label: "trends", value: "+72%" },
      { source: "x", label: "x", value: "2.4k t/h" },
      { source: "news", label: "news", value: "31 art." },
    ],
    sources: [
      { name: "Google Trends", value: "+72%", fill: 40 },
      { name: "Wikimedia", value: "4 200 vues/h", fill: 28 },
      { name: "X velocity", value: "2 400 t/h", fill: 45 },
      { name: "Google News", value: "31 articles", fill: 52 },
      { name: "GSC historique", value: "Top 15%", fill: 65 },
    ],
    reporter: r("jp"),
    reporterRationale: {
      lead: "Spécialiste tennis de la rédaction",
      stats: "8 articles Discover Sport · score thématique 79",
    },
    altReporters: [r("ad")],
    refs: [
      "L'Équipe · 16 mai — Le jeune Mpetshi Perricard, l'arme secrète française",
    ],
  },
  {
    id: "s07",
    rank: 7,
    title: "Eurovision 2026 : la France parmi les favoris des bookmakers à 5 jours du concours",
    theme: "Culture",
    score: 52,
    rationale:
      "Pic prévisible en montée. À surveiller dans les 48 h ; faible signal aujourd'hui mais bonne projection.",
    signals: [
      { source: "trends", label: "trends", value: "+44%" },
      { source: "news", label: "news", value: "26 art." },
    ],
    sources: [
      { name: "Google Trends", value: "+44%", fill: 30 },
      { name: "Wikimedia", value: "2 800 vues/h", fill: 20 },
      { name: "X velocity", value: "1 400 t/h", fill: 32 },
      { name: "Google News", value: "26 articles", fill: 48 },
      { name: "GSC historique", value: "Top 18%", fill: 58 },
    ],
    reporter: r("cr"),
    reporterRationale: {
      lead: "Suivi Eurovision pour PM depuis 3 éditions",
      stats: "5 articles Discover · 81 score Culture",
    },
    altReporters: [r("sm")],
    refs: [
      "Eurovision.tv · 17 mai — Les nouvelles cotes des bookmakers",
    ],
  },
  {
    id: "s08",
    rank: 8,
    title: "Drame en Méditerranée : 41 disparus dans le naufrage d'une embarcation au large de Lampedusa",
    theme: "International",
    score: 38,
    rationale:
      "Sujet important éditorialement mais faible affinité Discover pour Paris Match. À couvrir, sans miser dessus en visibilité.",
    signals: [
      { source: "news", label: "news", value: "188 art." },
      { source: "trends", label: "trends", value: "+24%" },
    ],
    sources: [
      { name: "Google Trends", value: "+24%", fill: 22 },
      { name: "Wikimedia", value: "900 vues/h", fill: 10 },
      { name: "X velocity", value: "780 t/h", fill: 18 },
      { name: "Google News", value: "188 articles", fill: 88 },
      { name: "GSC historique", value: "Top 28%", fill: 30 },
    ],
    reporter: r("lm"),
    reporterRationale: {
      lead: "Référente International",
      stats: "5 articles Discover · score thématique 71",
    },
    altReporters: [r("ad"), r("ev")],
    refs: [
      "ANSA · 18 mai 04:12 — Naufrage Lampedusa, 41 dispersi confermati",
    ],
  },
  {
    id: "s09",
    rank: 9,
    title: "Tempête Edmond : 1,2 million de foyers privés d'électricité dans l'ouest",
    theme: "Société",
    score: 32,
    rationale:
      "Couverture nécessaire pour service mais peu de potentiel Discover. À traiter en brève, allègement de production.",
    signals: [
      { source: "news", label: "news", value: "144 art." },
      { source: "trends", label: "trends", value: "+18%" },
    ],
    sources: [
      { name: "Google Trends", value: "+18%", fill: 18 },
      { name: "Wikimedia", value: "300 vues/h", fill: 8 },
      { name: "X velocity", value: "420 t/h", fill: 12 },
      { name: "Google News", value: "144 articles", fill: 78 },
      { name: "GSC historique", value: "Top 35%", fill: 22 },
    ],
    reporter: r("ev"),
    reporterRationale: {
      lead: "Format breaking court",
      stats: "12 articles Discover · 83 score breaking",
    },
    altReporters: [r("lm")],
    refs: [
      "Météo-France · 18 mai 03:30 — Alerte rouge maintenue sur 4 départements",
    ],
  },
  {
    id: "s10",
    rank: 10,
    title: "Municipales 2026 : sondage choc à Marseille à 8 mois du scrutin",
    theme: "Politique",
    score: 28,
    rationale:
      "Faible signal externe, à recycler éventuellement plus tard. Pas prioritaire dans le briefing du jour.",
    signals: [
      { source: "news", label: "news", value: "21 art." },
      { source: "gsc", label: "gsc", value: "top 22%" },
    ],
    sources: [
      { name: "Google Trends", value: "+8%", fill: 8 },
      { name: "Wikimedia", value: "240 vues/h", fill: 6 },
      { name: "X velocity", value: "320 t/h", fill: 10 },
      { name: "Google News", value: "21 articles", fill: 38 },
      { name: "GSC historique", value: "Top 22%", fill: 42 },
    ],
    reporter: r("tb"),
    reporterRationale: {
      lead: "Référent politique nationale",
      stats: "6 articles Discover · 76 score politique",
    },
    altReporters: [r("ad")],
    refs: [
      "Ifop · 17 mai — Baromètre municipales Marseille",
    ],
  },
];

/* ----- Tier classifier ----- */

export const tierFromScore = (score) => {
  if (score >= 70) return "high";
  if (score >= 40) return "medium";
  return "low";
};

export const tierLabel = {
  high: "Signal fort",
  medium: "Signal moyen",
  low: "Signal faible",
};

/* ----- Reporter "moi" view : Sophie Martin a 3 sujets ----- */

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
