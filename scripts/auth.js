/* ===================================================================
   Auth gate — modal de connexion simple (gate cosmétique côté client).

   ⚠️ Ceci N'EST PAS de la sécurité réelle :
     - tout le check se fait dans le navigateur
     - le hash est facile à reverse engineer
     - les devtools permettent de bypass

   C'est un sas d'accès pour le POC en attendant Vercel Password
   Protection (native, vraie protection au niveau du déploiement).
*/

const STORAGE_KEY = "tbr-auth-session";
const SESSION_DAYS = 7;

const EXPECTED_EMAIL = "contact@theblackroom.io";
// SHA-256 de "#tbr2026" — calculé via `printf '%s' '#tbr2026' | shasum -a 256`
const EXPECTED_PASSWORD_HASH =
  "d8e14d7756a51862fcba3930e430079a3396744ca05b574b4d42534b71306102";

/* -------------------------------------------------------------------
   Helpers
   ------------------------------------------------------------------- */

const sha256 = async (text) => {
  const buffer = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text),
  );
  return Array.from(new Uint8Array(buffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
};

const isSessionValid = () => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return false;
    const { expires } = JSON.parse(raw);
    return typeof expires === "number" && Date.now() < expires;
  } catch {
    return false;
  }
};

const persistSession = () => {
  const expires = Date.now() + SESSION_DAYS * 24 * 60 * 60 * 1000;
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ expires }));
};

const clearSession = () => {
  localStorage.removeItem(STORAGE_KEY);
};

/* -------------------------------------------------------------------
   Gate UI
   ------------------------------------------------------------------- */

const lock = (gate) => {
  document.documentElement.classList.add("is-locked");
  gate?.classList.add("is-open");
  setTimeout(() => gate?.querySelector("#auth-email")?.focus(), 0);
};

const unlock = (gate) => {
  document.documentElement.classList.remove("is-locked");
  gate?.classList.remove("is-open");
};

const setError = (gate, message) => {
  const errorEl = gate.querySelector("#auth-error");
  if (!errorEl) return;
  errorEl.textContent = message || "";
  errorEl.classList.toggle("is-visible", Boolean(message));
};

const attachSubmitHandler = (gate) => {
  const form = gate.querySelector("#auth-form");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    setError(gate, "");

    const email = gate.querySelector("#auth-email").value.trim().toLowerCase();
    const password = gate.querySelector("#auth-password").value;

    if (!email || !password) {
      setError(gate, "Email et mot de passe requis.");
      return;
    }

    const submitBtn = form.querySelector("button[type='submit']");
    submitBtn.disabled = true;
    submitBtn.textContent = "Vérification…";

    const passHash = await sha256(password);
    const mailOk = email === EXPECTED_EMAIL;
    const passOk = passHash === EXPECTED_PASSWORD_HASH;

    if (mailOk && passOk) {
      persistSession();
      unlock(gate);
      // Reset le formulaire pour la prochaine ouverture
      form.reset();
    } else {
      setError(gate, "Identifiants invalides.");
      submitBtn.disabled = false;
      submitBtn.textContent = "Accéder";
      gate.querySelector("#auth-password").select();
    }
  });
};

/* -------------------------------------------------------------------
   Init
   ------------------------------------------------------------------- */

const initAuth = () => {
  const gate = document.querySelector("#auth-gate");
  if (!gate) return;

  attachSubmitHandler(gate);

  // L'inline script du <head> a déjà posé .is-locked sur <html> si nécessaire.
  // Ici on resynchronise au cas où la session aurait expiré entre-temps.
  if (!isSessionValid()) {
    lock(gate);
  } else {
    unlock(gate);
  }

  // Bouton de déconnexion optionnel (élément avec [data-auth-logout])
  document.querySelectorAll("[data-auth-logout]").forEach((el) => {
    el.addEventListener("click", (event) => {
      event.preventDefault();
      clearSession();
      lock(gate);
    });
  });
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initAuth);
} else {
  initAuth();
}
