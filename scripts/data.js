/* ===================================================================
   Constantes partagées — utilisées par briefing.js et autres vues.

   Plus de pool de rédacteurs ici : le briefing global est désormais
   neutre (pas d'assignation à un journaliste). Cette logique reviendra
   sous forme de "projets par site" + byline scraping (cf. roadmap).
   =================================================================== */

// Doit rester aligné avec server/scoring/score.py / tier_from_score()
// Seuils sur l'echelle d'affichage /100 (post-rescale x100/65).
export const tierFromScore = (score) => {
  if (score >= 77) return "high";
  if (score >= 46) return "medium";
  return "low";
};

export const tierLabel = {
  high: "Signal fort",
  medium: "Signal moyen",
  low: "Signal faible",
};
