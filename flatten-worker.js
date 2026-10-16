// Copyright 2026 Felipe Navarro Murcia. Licensed under the Apache License, Version 2.0 (see LICENSE and NOTICE).
/* Builds the clean model in the browser: runs tools/flatten.py (unchanged) with Pyodide (numpy + scipy).
   Message in: { glb: ArrayBuffer }. Messages out: { step: 1..3 }, then { json } or { error }. */
const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v0.27.7/full/';
importScripts(PYODIDE + 'pyodide.js');

onmessage = async e => {
  try {
    postMessage({ step: 1 });
    const py = await loadPyodide({ indexURL: PYODIDE });
    postMessage({ step: 2 });
    await py.loadPackage(['numpy', 'scipy']);
    postMessage({ step: 3 });
    const srcs = await Promise.all(['tools/flatten.py', 'tools/glbload.py'].map(u =>
      fetch(u).then(r => { if (!r.ok) throw new Error(u + ': ' + r.status); return r.text(); })));
    py.FS.mkdirTree('/w');
    py.FS.writeFile('/w/flatten.py', srcs[0]);
    py.FS.writeFile('/w/glbload.py', srcs[1]);
    py.FS.writeFile('/w/scan.glb', new Uint8Array(e.data.glb));
    py.runPython("import sys\nsys.path.insert(0, '/w')\nimport flatten\nflatten.main('/w/scan.glb', '/w/out.json')");
    postMessage({ json: py.FS.readFile('/w/out.json', { encoding: 'utf8' }) });
  } catch (err) {
    postMessage({ error: String((err && err.message) || err) });
  }
};
