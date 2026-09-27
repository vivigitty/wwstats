export default {
  title: "Weekend Wickets",
  root: "src",
  theme: ["glacier", "near-midnight"],
  style: "style.css",
  toc: false,
  pager: false,
  sidebar: false,
  header: "",
  footer: ({ title }) =>
    `<div class="ww-footer">${title} · built from CricHeroes scorecards · updated ${new Date().toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}</div>`,
  // Windows maps "python3" to a Microsoft Store stub, so call "python" directly.
  interpreters: { ".py": [process.env.PYTHON ?? "python"] },
  // Set this to "/<repo-name>/" when publishing to a GitHub Pages project site.
  base: process.env.SITE_BASE ?? "/",
};
