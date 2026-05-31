/* ===================================================================
   Constantes partagées — utilisées par briefing.js et autres vues.

   Plus de pool de rédacteurs ici : le briefing global est désormais
   neutre (pas d'assignation à un journaliste). Cette logique reviendra
   sous forme de "projets par site" + byline scraping (cf. roadmap).
   =================================================================== */

// Doit rester aligné avec server/scoring/score.py / tier_from_score()
// Seuils sur l'echelle d'affichage (post-rescale x1.2 clamp 100).
// 100 reste exceptionnel par construction (internal max ~78 en pratique).
export const tierFromScore = (score) => {
  if (score >= 60) return "high";
  if (score >= 36) return "medium";
  return "low";
};

export const tierLabel = {
  high: "Signal fort",
  medium: "Signal moyen",
  low: "Signal faible",
};
