"""Helper functions for geometry, I/O, field operations."""

import json
import math
import statistics
import collections
import base64
import mimetypes
from pathlib import Path

from config import (
    POINTS_FILENAME,
    COMMUNITY_FILENAME,
    CLUSTER_DIST_M,
    LOGO_DIR,
    INFORMATION_FILE,
    LOGOS_URLS_FILE,
    render_markdown,
)


# ---------- I/O & Coords ----------
def _candidates(name: str):
    """Find potential paths for a data file."""
    base = Path(__file__).parent
    return [
        base / "data" / name,
        base / "graphics" / "data" / name,
        Path.cwd() / "data" / name,
        Path.cwd() / "graphics" / "data" / name,
    ]


def _read_json_any(paths):
    """Try to read JSON from multiple paths."""
    for p in paths:
        try:
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _to_float(x):
    """Safe float conversion."""
    try:
        return float(x)
    except Exception:
        return None


def _finite_latlon(lat, lon):
    """Check if lat/lon are valid."""
    if lat is None or lon is None:
        return False
    try:
        if math.isnan(lat) or math.isnan(lon):
            return False
    except Exception:
        pass
    return -90 <= lat <= 90 and -180 <= lon <= 180


# ---------- Points Loading ----------
def _load_points_records():
    """Load all point features from GeoJSON."""
    gj = _read_json_any(_candidates(POINTS_FILENAME))
    if gj is None:
        raise FileNotFoundError(f"{POINTS_FILENAME} not found in ./data or ./graphics/data")
    out, idx = [], 0
    for feat in gj.get("features", []):
        geom = feat.get("geometry") or {}
        props = feat.get("properties") or {}
        t = geom.get("type")
        if t == "Point":
            lon, lat = (geom.get("coordinates") or [None, None])[:2]
            lat, lon = _to_float(lat), _to_float(lon)
            if _finite_latlon(lat, lon):
                out.append({"id": idx, "lat": lat, "lon": lon, "props": props})
                idx += 1
        elif t == "MultiPoint":
            for c in geom.get("coordinates") or []:
                lon, lat = (c[:2] + [None, None])[:2]
                lat, lon = _to_float(lat), _to_float(lon)
                if _finite_latlon(lat, lon):
                    out.append({"id": idx, "lat": lat, "lon": lon, "props": props})
                    idx += 1
    return out


def _build_key_order(items):
    """Build ordered list of all property keys from records."""
    order, seen = [], set()
    if items:
        for k in (items[0].get("props") or {}).keys():
            order.append(k)
            seen.add(k)
    for it in items:
        for k in (it.get("props") or {}).keys():
            if k not in seen:
                order.append(k)
                seen.add(k)
    return order


def _points_centroid(items):
    """Get centroid of point set (lat, lon, zoom)."""
    if not items:
        return (49.2827, -123.1207, 9)
    lats = [it["lat"] for it in items]
    lons = [it["lon"] for it in items]
    return (sum(lats) / len(lats), sum(lons) / len(lons), 9)


def _points_bbox(items):
    """Get bbox (s, w, n, e) from points."""
    if not items:
        return (49.0, -123.6, 49.6, -122.2)
    lats = [it["lat"] for it in items]
    lons = [it["lon"] for it in items]
    return (min(lats), min(lons), max(lats), max(lons))


# ---------- Extent Normalization ----------
def _canon_extent(x: str):
    """Normalize extent string to one of 4 canonical buckets."""
    if x is None:
        return "Regional and broader"
    s = str(x).strip().lower()
    if not s:
        return "Regional and broader"
    if s in {"site-specific", "site specifc", "site specifc.", "site"}:
        return "Site-specific"
    if s in {"community", "community-level", "community level"}:
        return "Community"
    if s in {"sub-regional", "subregional", "sub region", "sub region al"}:
        return "Sub-regional"
    if s in {
        "regional",
        "region",
        "boarder",
        "broader",
        "border",
        "regional and boarder",
        "regional & boarder",
        "regional and broader",
    }:
        return "Regional and broader"
    return "Regional and broader"


# ---------- Distances / Snapping ----------
def _haversine_m(lat1, lon1, lat2, lon2):
    """Calculate distance between two points in meters."""
    R = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _cluster_and_snap(points, tol_m=CLUSTER_DIST_M):
    """Snap every point to the centroid of its <=tol_m cluster (no jitter)."""
    if not points:
        return {}
    groups = []
    for it in points:
        lat = it["lat"]
        lon = it["lon"]
        matched = None
        for g in groups:
            if _haversine_m(lat, lon, g["lat"], g["lon"]) <= tol_m:
                g["members"].append(it)
                n = len(g["members"])
                g["lat"] += (lat - g["lat"]) / n
                g["lon"] += (lon - g["lon"]) / n
                matched = g
                break
        if matched is None:
            groups.append({"lat": lat, "lon": lon, "members": [it]})
    id2disp = {}
    for g in groups:
        cy, cx = g["lat"], g["lon"]
        for m in g["members"]:
            id2disp[m["id"]] = (cy, cx)
    return id2disp


# ---------- Polygon → Polyline Helpers ----------
def _swap_lonlat_if_needed(sample_lon, sample_lat):
    """Detect if coords are lat/lon (swapped) instead of lon/lat."""
    if not sample_lon or not sample_lat:
        return False
    lon_abs = [abs(x) for x in sample_lon if x is not None]
    lat_abs = [abs(y) for y in sample_lat if y is not None]
    if not lon_abs or not lat_abs:
        return False
    lon_med = statistics.median(lon_abs)
    lat_med = statistics.median(lat_abs)
    return lon_med < 70 and lat_med > 80


def _collect_lonlat_samples(gj, max_n=5000):
    """Collect coordinate samples from GeoJSON."""
    lons, lats = [], []
    if not gj or gj.get("type") != "FeatureCollection":
        return lons, lats
    count = 0
    for f in gj.get("features", []):
        g = f.get("geometry") or {}
        t = g.get("type")
        c = g.get("coordinates")
        if t == "MultiPolygon":
            for poly in c or []:
                for ring in poly or []:
                    for p in ring or []:
                        if isinstance(p, (list, tuple)) and len(p) >= 2:
                            lons.append(_to_float(p[0]))
                            lats.append(_to_float(p[1]))
                            count += 1
                            if count >= max_n:
                                return lons, lats
        elif t == "Polygon":
            for ring in c or []:
                for p in ring or []:
                    if isinstance(p, (list, tuple)) and len(p) >= 2:
                        lons.append(_to_float(p[0]))
                        lats.append(_to_float(p[1]))
                        count += 1
                        if count >= max_n:
                            return lons, lats
        elif t in ("LineString", "MultiLineString"):
            seqs = [c] if t == "LineString" else c
            for ln in seqs or []:
                for p in ln or []:
                    if isinstance(p, (list, tuple)) and len(p) >= 2:
                        lons.append(_to_float(p[0]))
                        lats.append(_to_float(p[1]))
                        count += 1
                        if count >= max_n:
                            return lons, lats
    return lons, lats


def _poly_exact_to_lines_feature(f, swap, close=True):
    """Convert polygon to exact line strings."""
    g = f.get("geometry") or {}
    t = g.get("type")
    coords = g.get("coordinates") or []

    def conv(p):
        if not (isinstance(p, (list, tuple)) and len(p) >= 2):
            return None
        lon, lat = _to_float(p[0]), _to_float(p[1])
        if swap:
            lon, lat = lat, lon
        return [lon, lat] if _finite_latlon(lat, lon) else None

    lines = []
    if t == "Polygon":
        for ring in coords or []:
            acc = [q for p in (ring or []) if (q := conv(p))]
            if close and len(acc) >= 2 and acc[0] != acc[-1]:
                acc.append(acc[0])
            if len(acc) >= 2:
                lines.append(acc)
    elif t == "MultiPolygon":
        for poly in coords or []:
            for ring in poly or []:
                acc = [q for p in (ring or []) if (q := conv(p))]
                if close and len(acc) >= 2 and acc[0] != acc[-1]:
                    acc.append(acc[0])
                if len(acc) >= 2:
                    lines.append(acc)
    else:
        return None
    if not lines:
        return None
    return {
        "type": "Feature",
        "properties": f.get("properties") or {},
        "geometry": {"type": "MultiLineString", "coordinates": lines},
    }


def _clip_bbox(lat, lon, bbox):
    """Check if point is within bbox."""
    s, w, n, e = bbox
    return (s <= lat <= n) and (w <= lon <= e)


def _poly_thinclip_to_lines_feature(f, swap, bbox, pad_deg, stride, close=True):
    """Convert polygon to thinned/clipped line strings."""
    g = f.get("geometry") or {}
    t = g.get("type")
    coords = g.get("coordinates") or []
    south, west, north, east = bbox
    pad_bbox = (south - pad_deg, west - pad_deg, north + pad_deg, east + pad_deg)

    def conv(p):
        if not (isinstance(p, (list, tuple)) and len(p) >= 2):
            return None
        lon, lat = _to_float(p[0]), _to_float(p[1])
        if swap:
            lon, lat = lat, lon
        return [lon, lat] if _finite_latlon(lat, lon) else None

    lines = []
    if t == "Polygon":
        for ring in coords or []:
            acc = []
            for i, p in enumerate(ring or []):
                q = conv(p)
                if not q:
                    continue
                if i == 0 or (stride <= 1) or (i % stride == 0):
                    if _clip_bbox(q[1], q[0], pad_bbox):
                        acc.append(q)
            if close and len(acc) >= 2 and acc[0] != acc[-1]:
                acc.append(acc[0])
            if len(acc) >= 2:
                lines.append(acc)
    elif t == "MultiPolygon":
        for poly in coords or []:
            for ring in poly or []:
                acc = []
                for i, p in enumerate(ring or []):
                    q = conv(p)
                    if not q:
                        continue
                    if i == 0 or (stride <= 1) or (i % stride == 0):
                        if _clip_bbox(q[1], q[0], pad_bbox):
                            acc.append(q)
                if close and len(acc) >= 2 and acc[0] != acc[-1]:
                    acc.append(acc[0])
                if len(acc) >= 2:
                    lines.append(acc)
    else:
        return None

    if not lines:
        return None
    return {
        "type": "Feature",
        "properties": f.get("properties") or {},
        "geometry": {"type": "MultiLineString", "coordinates": lines},
    }


def _sanitize_bounds_to_lines(raw_gj, pts_bbox, pad_deg, stride, exact=False):
    """Convert GeoJSON boundaries to line strings with optional thinning/clipping."""
    if not raw_gj or raw_gj.get("type") != "FeatureCollection":
        return None, {"features": 0, "types": {}, "swap": False}
    sample_lons, sample_lats = _collect_lonlat_samples(raw_gj)
    swap = _swap_lonlat_if_needed(sample_lons, sample_lats)
    out = {"type": "FeatureCollection", "features": []}
    type_counts = collections.Counter()
    south, west, north, east = pts_bbox
    for f in raw_gj.get("features", []):
        g = f.get("geometry") or {}
        t = g.get("type")
        type_counts[t or "None"] += 1
        if t in ("Polygon", "MultiPolygon"):
            feat = (
                _poly_exact_to_lines_feature(f, swap)
                if exact
                else _poly_thinclip_to_lines_feature(
                    f, swap, (south, west, north, east), pad_deg, max(1, int(stride))
                )
            )
            if feat:
                out["features"].append(feat)
        elif t in ("LineString", "MultiLineString"):
            coords = g.get("coordinates") or []
            seqs = [coords] if t == "LineString" else coords
            parts = []
            for ln in seqs or []:
                acc = []
                for i, p in enumerate(ln or []):
                    if not (isinstance(p, (list, tuple)) and len(p) >= 2):
                        continue
                    lon, lat = _to_float(p[0]), _to_float(p[1])
                    if swap:
                        lon, lat = lat, lon
                    if not _finite_latlon(lat, lon):
                        continue
                    if exact:
                        acc.append([lon, lat])
                    else:
                        if i == 0 or (int(stride) <= 1) or (i % stride == 0):
                            if _clip_bbox(lat, lon, (south - pad_deg, west - pad_deg, north + pad_deg, east + pad_deg)):
                                acc.append([lon, lat])
                if len(acc) >= 2:
                    parts.append(acc)
            if parts:
                out["features"].append(
                    {
                        "type": "Feature",
                        "properties": f.get("properties") or {},
                        "geometry": {
                            "type": t,
                            "coordinates": (parts if t == "MultiLineString" else parts[0]),
                        },
                    }
                )
    meta = {"features": len(out["features"]), "types": dict(type_counts), "swap": swap}
    return (out if out["features"] else None), meta


# ---------- Field Finding ----------
def _find_field(key_order, name_exact: str, contains_ok=True):
    """Find field by exact name or substring."""
    target = name_exact.strip().lower()
    for k in key_order:
        if k.strip().lower() == target:
            return k
    if contains_ok:
        for k in key_order:
            if target in k.strip().lower():
                return k
    return None


# ---------- Features & Display ----------
def _disp_latlon(item, id2disp_snap=None):
    """Get displayed (snapped) lat/lon for a point, or original if not snapped."""
    if id2disp_snap is None:
        return (item.get("lat"), item.get("lon"))
    item_id = item.get("id")
    if item_id in id2disp_snap:
        lat, lon = id2disp_snap[item_id]
        return (lat, lon)
    return (item.get("lat"), item.get("lon"))


def _rows_to_fc(rows, key, id2disp_snap=None):
    """Convert list of point rows to GeoJSON FeatureCollection."""
    if id2disp_snap is None:
        id2disp_snap = {}
    features = []
    for row in rows:
        lat, lon = _disp_latlon(row, id2disp_snap)
        props = dict(row.get("props") or {})
        props["__extent_canon__"] = key
        feat = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        }
        features.append(feat)
    return {"type": "FeatureCollection", "features": features}


# ---------- Information Helpers ----------
def load_information_markdown():
    """Load and convert information.md to HTML."""
    if INFORMATION_FILE.exists():
        try:
            md_content = INFORMATION_FILE.read_text(encoding="utf-8")
            html_content = render_markdown(md_content)
            return html_content
        except Exception:
            return "<p style='color:#d32f2f'>Error loading information.md</p>"
    else:
        return "<p style='color:#d32f2f'>information.md not found</p>"


def logo_files_to_data_uris():
    """Convert logo files to data URIs."""
    items = []
    if LOGO_DIR.exists() and LOGO_DIR.is_dir():
        for p in sorted(LOGO_DIR.iterdir()):
            if not p.is_file():
                continue
            ext = p.suffix.lower()
            if ext not in {".png", ".jpg", ".jpeg", ".svg", ".webp"}:
                continue
            mime, _ = mimetypes.guess_type(p.name)
            if mime is None:
                if ext == ".svg":
                    mime = "image/svg+xml"
                elif ext == ".webp":
                    mime = "image/webp"
                elif ext in {".jpg", ".jpeg"}:
                    mime = "image/jpeg"
                else:
                    mime = "image/png"
            try:
                if ext == ".svg":
                    raw = p.read_text(encoding="utf-8")
                    b64 = base64.b64encode(raw.encode("utf-8")).decode("ascii")
                else:
                    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
                items.append({"name": p.name, "data_uri": f"data:{mime};base64,{b64}"})
            except Exception:
                continue
    return items


def load_logos_urls():
    """Load logo URLs from logos_urls.json."""
    urls = {}
    if LOGOS_URLS_FILE.exists():
        try:
            urls = json.loads(LOGOS_URLS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return urls
