# CLAUDE.md

Public, client-side version of the Home 3D Planner (static site on GitHub Pages: https://lipeandres.github.io/home-3d-planner/). Personal scans and layouts belong in the private `home_3d` repo, never here.

- No build step and no server code: `index.html` + `flatten-worker.js` + `tools/`. Test with `python3 -m http.server 8801`; use a GLB from `../home_3d` served temporarily (symlink `_test.glb`, git-ignored, delete after).
- Scans, edits and layouts live in the visitor's browser (IndexedDB `home3d` for scans + clean model, localStorage `home3d-*-<scanKey>` for the rest). Never add uploads or network calls with user data.
- `tools/flatten.py` runs unchanged in Pyodide (v0.27.7 pinned in `flatten-worker.js`); keep it numpy/scipy-only.
- Apache-2.0: keep `LICENSE`, `NOTICE`, file headers and the "Created by Felipe Navarro Murcia" sidebar credit plus third-party credits (sidebar + NOTICE + README) in sync when adding libraries.
- Pages deploys from `main` root; push to publish.
