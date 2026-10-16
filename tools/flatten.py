#!/usr/bin/env python3
# Copyright 2026 Felipe Navarro Murcia. Licensed under the Apache License, Version 2.0 (see LICENSE and NOTICE).
"""Flatten a Polycam GLB scan into a clean, axis-aligned house model (walls + floor/ceiling slabs).

usage: .venv/bin/python tools/flatten.py new_home_2.glb new_home_2.clean.json

Method (per scene-graph "Story"):
  1. Wall alignment: the dominant wall-normal direction (mod 90 deg) defines a local frame (u, v).
  2. Floor / ceiling height: robust plane fit to up-/down-facing surfaces, flattened to one level.
  3. Walls: surfaces whose normal is horizontal, within the story's height band, are histogrammed along u and v;
     peaks become wall lines, their coverage along the other axis becomes wall segments (gaps <= BRIDGE are bridged).
  4. Floor / ceiling slabs: occupancy raster of the up-/down-facing surfaces, closed and hole-filled, greedy-meshed
     into rectangles.
Everything else (furniture, clutter, scan noise, holes) is dropped. Output coordinates are in the local frame:
world x = u cos(t) - v sin(t), world z = u sin(t) + v cos(t), with t = "theta" in the JSON.
"""
import json, sys
import numpy as np
from scipy import ndimage as ndi
from glbload import load_stories

BAND_LO, BAND_HI = 0.30, 0.30      # wall band: floor+LO .. ceil-HI (ignores floor/ceiling edge clutter)
NORMAL_COS = 0.9                   # |n . axis| for a surface to count as a wall facing that axis
LINE_BIN, LINE_SIGMA = 0.04, 1.0   # 1D histogram bin (m) and smoothing (bins) for wall lines
LINE_MIN_AREA = 0.55               # min surface area (m2) in a line bin to be a wall candidate
MERGE = 0.18                       # candidate lines closer than this are the two faces of one wall
RUN_BIN, RUN_MIN_AREA = 0.05, 0.03 # along-wall coverage bin (m) and area needed to count as wall
BRIDGE, MIN_LEN = 0.20, 0.45       # bridge scan gaps up to this; drop walls shorter than this
CELL = 0.10                        # slab raster cell
CLOSE_R, FILL_AREA, MIN_COMP = 3, 0.8, 1.5


def tri_stats(t):
    c = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]); l = np.linalg.norm(c, axis=1)
    return t.mean(1), c / np.maximum(l, 1e-12)[:, None], l / 2


def fit_level(cen, w, y_guess, tol=0.35):
    """Weighted plane fit around y_guess, returns (flat height at centroid, slope_x, slope_z, n_pts, centroid xz)."""
    m = np.abs(cen[:, 1] - y_guess) < tol
    for _ in range(5):
        P, ww = cen[m], np.sqrt(w[m])
        A = np.c_[P[:, 0], P[:, 2], np.ones(len(P))] * ww[:, None]
        k = np.linalg.lstsq(A, P[:, 1] * ww, rcond=None)[0]
        m = np.abs(cen[:, 1] - (k[0] * cen[:, 0] + k[1] * cen[:, 2] + k[2])) < 0.05
    c = np.average(cen[m][:, [0, 2]], axis=0, weights=w[m])
    return k[0] * c[0] + k[1] * c[1] + k[2], k[0], k[1], int(m.sum()), c


def peak_level(cen, n, w, up, lo, hi):
    msk = (n[:, 1] > 0.9) if up else (n[:, 1] < -0.9)
    msk &= (cen[:, 1] > lo) & (cen[:, 1] < hi)
    h, ed = np.histogram(cen[msk, 1], bins=np.arange(lo, hi, 0.05), weights=w[msk])
    return ed[h.argmax()] + 0.025, msk


def greedy_rects(mask, u0, v0, cell):
    """mask[iu, iv] -> list of [u0,v0,u1,v1] rectangles (merge runs along v, then identical runs along u)."""
    rects, open_runs = [], {}
    for iu in range(mask.shape[0] + 1):
        row = mask[iu] if iu < mask.shape[0] else np.zeros(mask.shape[1], bool)
        d = np.diff(np.r_[0, row.astype(np.int8), 0])
        runs = set(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))
        for r in list(open_runs):
            if r not in runs:
                s = open_runs.pop(r); rects.append([u0 + s * cell, v0 + r[0] * cell, u0 + iu * cell, v0 + r[1] * cell])
        for r in runs:
            open_runs.setdefault(r, iu)
    return [[round(x, 3) for x in r] for r in rects]


def slab(cen, w, msk, level, u0, u1, v0, v1):
    """Occupancy raster of surfaces near `level` -> rectangles."""
    sel = msk & (np.abs(cen[:, 1] - level) < 0.15)
    nu, nv = int(np.ceil((u1 - u0) / CELL)), int(np.ceil((v1 - v0) / CELL))
    area, _, _ = np.histogram2d(cen[sel, 0], cen[sel, 2], bins=[nu, nv], range=[[u0, u0 + nu * CELL], [v0, v0 + nv * CELL]], weights=w[sel])
    occ = area > 0.0015
    occ = ndi.binary_closing(occ, structure=ndi.generate_binary_structure(2, 2), iterations=CLOSE_R)
    holes = ndi.binary_fill_holes(occ) & ~occ
    lab, nlab = ndi.label(holes)
    if nlab:
        sizes = ndi.sum(holes, lab, range(1, nlab + 1))
        for i, s in enumerate(sizes, 1):
            if s * CELL * CELL <= FILL_AREA: occ[lab == i] = True
    lab, nlab = ndi.label(occ)
    if nlab:
        sizes = ndi.sum(occ, lab, range(1, nlab + 1))
        for i, s in enumerate(sizes, 1):
            if s * CELL * CELL < MIN_COMP: occ[lab == i] = False
    return greedy_rects(occ, u0, v0, CELL)


def find_lines(p, w):
    """1D wall-line candidates along one axis -> list of (center, thickness)."""
    lo, hi = p.min() - 0.2, p.max() + 0.2
    bins = np.arange(lo, hi + LINE_BIN, LINE_BIN)
    h, _ = np.histogram(p, bins=bins, weights=w)
    hs = ndi.gaussian_filter1d(h, LINE_SIGMA)
    cands = [i for i in range(1, len(hs) - 1) if hs[i] >= hs[i - 1] and hs[i] > hs[i + 1] and hs[i] >= LINE_MIN_AREA]
    centers = [lo + (i + 0.5) * LINE_BIN for i in cands]; mass = [hs[i] for i in cands]
    groups = []                                       # merge faces of the same wall
    for c, m in sorted(zip(centers, mass)):
        if groups and c - groups[-1][-1][0] < MERGE: groups[-1].append((c, m))
        else: groups.append([(c, m)])
    out = []
    for g in groups:
        cs, ms = np.array([x[0] for x in g]), np.array([x[1] for x in g])
        out.append((float(np.average(cs, weights=ms)), float(np.clip(cs.max() - cs.min() + 0.06, 0.10, 0.30))))
    return out


def wall_segments(pl, ql, wl, p0, t):
    """Coverage of points near line p0 along q -> [(q0, q1)] runs."""
    sel = np.abs(pl - p0) < t / 2 + 0.08
    if sel.sum() < 5: return []
    q = ql[sel]; lo, hi = q.min(), q.max()
    nb = int(np.ceil((hi - lo) / RUN_BIN)) + 1
    h, _ = np.histogram(q, bins=nb, range=(lo, lo + nb * RUN_BIN), weights=wl[sel])
    on = h >= RUN_MIN_AREA
    gap = int(round(BRIDGE / RUN_BIN))
    off = ~ndi.binary_closing(np.r_[False, on, False], structure=np.ones(gap + 1, bool))[1:-1] if gap else ~on
    on = ~off
    d = np.diff(np.r_[0, on.astype(np.int8), 0])
    runs = [(lo + a * RUN_BIN, lo + b * RUN_BIN) for a, b in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1))]
    return [(a, b) for a, b in runs if b - a >= MIN_LEN]


def main(src, dst):
    stories = load_stories(src)
    stats = {k: tri_stats(t) for k, t in stories.items()}
    # 1. wall alignment from all stories
    z = 0
    for cen, n, w in stats.values():
        m = np.abs(n[:, 1]) < 0.3
        phi = np.arctan2(n[m, 2], n[m, 0]); z += np.sum(w[m] * np.exp(4j * phi))
    theta = float(np.angle(z) / 4)
    c, s = np.cos(theta), np.sin(theta)
    print(f'wall alignment: {np.degrees(theta):.2f} deg')
    levels = []
    for name in sorted(stories):
        cen, n, w = stats[name]
        ylo, yhi = cen[:, 1].min(), cen[:, 1].max()
        loc = np.c_[cen[:, 0] * c + cen[:, 2] * s, cen[:, 1], -cen[:, 0] * s + cen[:, 2] * c]   # (u, y, v)
        nu = n[:, 0] * c + n[:, 2] * s; nv = -n[:, 0] * s + n[:, 2] * c                        # normal in local frame
        yf, mf = peak_level(loc, n, w, True, ylo, yhi)
        yc, mc = peak_level(loc, n, w, False, yf + 1.8, yhi + 0.05)
        floorY, sx, sz, nf, _ = fit_level(loc[mf], w[mf], yf)
        ceilY, cx, cz, nc, _ = fit_level(loc[mc], w[mc], yc)
        print(f'{name}: floor {floorY:.3f} (tilt {np.degrees(np.arctan(sx)):.2f},{np.degrees(np.arctan(sz)):.2f} deg, {nf} pts)  '
              f'ceil {ceilY:.3f} (tilt {np.degrees(np.arctan(cx)):.2f},{np.degrees(np.arctan(cz)):.2f})  height {ceilY - floorY:.2f}')
        u0, u1, v0, v1 = loc[:, 0].min(), loc[:, 0].max(), loc[:, 2].min(), loc[:, 2].max()
        floor = slab(loc, w, mf, floorY, u0, u1, v0, v1)
        ceil = slab(loc, w, mc, ceilY, u0, u1, v0, v1)
        band = (loc[:, 1] > floorY + BAND_LO) & (loc[:, 1] < ceilY - BAND_HI) & (np.abs(n[:, 1]) < 0.3)
        rng = np.random.default_rng(0)                    # sparse trace of the raw scan walls, for checking the result in the plan
        tr = np.flatnonzero(band); tr = rng.choice(tr, min(len(tr), 6000), replace=False)
        trace = [[round(float(loc[i, 0]), 2), round(float(loc[i, 2]), 2)] for i in tr]
        walls = []
        for axis, (p, q, nn) in {'u': (loc[:, 0], loc[:, 2], nu), 'v': (loc[:, 2], loc[:, 0], nv)}.items():
            sel = band & (np.abs(nn) > NORMAL_COS)
            for p0, t in find_lines(p[sel], w[sel]):
                for q0, q1 in wall_segments(p[sel], q[sel], w[sel], p0, t):
                    walls.append({'a': axis, 'p': round(p0, 3), 'q0': round(q0 - t / 2, 3), 'q1': round(q1 + t / 2, 3), 't': round(t, 3)})
        print(f'   walls {len(walls)}  floor rects {len(floor)}  ceiling rects {len(ceil)}')
        levels.append({'name': name, 'floorY': round(float(floorY), 3), 'ceilY': round(float(ceilY), 3), 'walls': walls, 'floor': floor, 'ceil': ceil, 'trace': trace})
    # sparse trace of up-facing surfaces between floors (stair treads) to help placing stairs by hand: [u, v, y above floor]
    for i, L in enumerate(levels[:-1]):
        cen, n, w = stats[sorted(stories)[i]]
        loc = np.c_[cen[:, 0] * c + cen[:, 2] * s, cen[:, 1], -cen[:, 0] * s + cen[:, 2] * c]
        m = (n[:, 1] > 0.8) & (loc[:, 1] > L['floorY'] + 0.3) & (loc[:, 1] < levels[i + 1]['floorY'] - 0.2)
        idx = np.flatnonzero(m); idx = np.random.default_rng(1).choice(idx, min(len(idx), 3000), replace=False)
        L['strace'] = [[round(float(loc[j, 0]), 2), round(float(loc[j, 2]), 2), round(float(loc[j, 1] - L['floorY']), 2)] for j in idx]
    json.dump({'source': src, 'theta': round(theta, 5), 'levels': levels}, open(dst, 'w'))
    print('wrote', dst)


if __name__ == '__main__':
    main(*sys.argv[1:3])
