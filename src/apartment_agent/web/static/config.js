// Frontend connection defaults.
//
// apiBase: base URL of the FastAPI backend (your Ubuntu box). Leave "" to use the same origin —
//   correct when the box itself serves this page. When hosted on GitHub Pages, set it to the box's
//   public/Tailscale URL (the Pages deploy workflow can generate this file from a repo variable).
// A token is NOT stored here — enter it via the ⚙ settings button so it never ships in the public
// page. Browser settings (localStorage) override these defaults.
window.AGENT_CONFIG = {
  apiBase: "",
};
