# Home 3D Planner

Explore a 3D scan of a house in your browser, check how furniture fits, and try out walls, floors, colours, doors, windows and stairs.
English, Português (Brasil) and Español (Latinoamérica).

**Open it:** https://lipeandres.github.io/home-3d-planner/

## How to use it

1. Export a scan from the Polycam app (*Export → glTF*, the free option, gives a `.zip`; *GLB* gives a `.glb`) and put the file on the device you will use. A `.gltf` with its `.bin` and textures also works (select them together).
2. Open the link above and choose that file (or drop it on the page). A `.zip` is unpacked in your browser and repacked as a `.glb`.
3. The first time, the app builds a clean model of the walls and floors from your scan. This takes about a minute and only happens once per scan.
4. Add furniture, edit walls and rooms, change the style, walk around inside.

**Privacy:** everything runs in your browser. Your scan, edits and furniture layouts are stored in this browser only (IndexedDB and localStorage) and are never uploaded.
Because of that, use **Save backup** now and then (sidebar, *House* section). Clearing the browser data deletes your work.

The page needs an internet connection to load its libraries (three.js, Pyodide, and fflate for `.zip` files) from public CDNs.

## Run it locally

No build step. Serve the folder over http (opening `index.html` as a file does not work, browsers block the worker):

```sh
python3 -m http.server 8000     # then open http://localhost:8000
```

## Files

| File | What |
|---|---|
| `index.html` | The whole app (three.js from a CDN) |
| `flatten-worker.js` | Web Worker that runs `tools/flatten.py` with Pyodide (numpy + scipy) |
| `tools/flatten.py`, `tools/glbload.py` | Builds the clean model (walls, floor and ceiling slabs) from a Polycam-style GLB |

## License and credit

Created by **Felipe Navarro Murcia**. Licensed under the [Apache License 2.0](LICENSE): free to use, share and modify, including for your own projects, as long as you keep the license, the [NOTICE](NOTICE) file and the credit. Please keep the "Created by" line in the app's sidebar if you host your own copy.

Third-party software, loaded at run time and not copied here: three.js (MIT), three-mesh-bvh (MIT), fflate (MIT), Pyodide (MPL-2.0), NumPy (BSD-3-Clause), SciPy (BSD-3-Clause). Full list in [NOTICE](NOTICE).
Not affiliated with or endorsed by Polycam.
