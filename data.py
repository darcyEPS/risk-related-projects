"""Data loading and initialization (runs once at startup)."""

from config import (
    POINTS_FILENAME,
    COMMUNITY_FILENAME,
    CLUSTER_DIST_M,
    ALWAYS_HIDDEN_FIELD_NAMES,
    DEFAULT_SELECTED_FIELDS,
)
from helpers import (
    _read_json_any,
    _load_points_records,
    _build_key_order,
    _points_bbox,
    _candidates,
    _cluster_and_snap,
    _find_field,
)

# Load all data once
ALL_POINTS = _load_points_records()
KEY_ORDER = _build_key_order(ALL_POINTS)
PTS_BBOX = _points_bbox(ALL_POINTS)
RAW_COMMUNITY = _read_json_any(_candidates(COMMUNITY_FILENAME))

# Safe default bounds [[s,w],[n,e]]
BOUNDS_DEFAULT = [[PTS_BBOX[0], PTS_BBOX[1]], [PTS_BBOX[2], PTS_BBOX[3]]]

# Precomputed SNAP display coords (500 m centroid snapping)
ID2DISP_SNAP = _cluster_and_snap(ALL_POINTS, tol_m=CLUSTER_DIST_M)

# Find extent and ecosystem service fields
EXTENT_FIELD = _find_field(KEY_ORDER, "Project extent")
ECO_YN_FIELD = _find_field(KEY_ORDER, "Does the Study Outcome Aim to Provide Ecosystem Services? (Y/N)")
ECO_HOW_FIELD = _find_field(KEY_ORDER, "How Does the Project Outcome Aim to Provide Ecosystem Services?")

# Determine which fields to hide
HIDDEN_FIELDS = {k for k in KEY_ORDER if k.strip().lower() in ALWAYS_HIDDEN_FIELD_NAMES}
