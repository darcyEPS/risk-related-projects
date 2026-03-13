"""Configuration constants and utilities."""

from pathlib import Path

# Markdown conversion: prefer the standard ``markdown`` library when
# available (used by the development environment); fall back to
# ``markdown-it-py`` which *is* bundled in the Pyodide build.
try:
    import markdown

    def render_markdown(text: str) -> str:
        return markdown.markdown(text, extensions=["tables"])
except ImportError:
    from markdown_it import MarkdownIt

    _md_parser = MarkdownIt("commonmark")

    def render_markdown(text: str) -> str:
        return _md_parser.render(text)


# --- FILE PATHS ---
POINTS_FILENAME = "WGSpoints.geojson"
COMMUNITY_FILENAME = "community_boundaries.geojson"

LOGO_DIR = Path(__file__).parent / "graphics" / "logos"
INFORMATION_FILE = Path(__file__).parent / "information.md"
LOGOS_URLS_FILE = Path(__file__).parent / "logos_urls.json"

# --- MAP ---
OSM_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_ATTR = "© OpenStreetMap contributors"

# --- GEOMETRY ---
DEFAULT_CLIP_PAD_DEG = 0.25
DEFAULT_VERTEX_STRIDE = 3
CLUSTER_DIST_M = 500.0  # 500m snap-to-centroid

# --- MAP DEFAULTS ---
SHOW_COMMUNITY_DEFAULT = True
EXACT_BOUNDS_DEFAULT = True
LINE_WIDTH_COMM_DEFAULT = 4.0
CLIP_PAD_DEFAULT = DEFAULT_CLIP_PAD_DEG
STRIDE_DEFAULT = DEFAULT_VERTEX_STRIDE

# --- EXTENTS (buckets for legend) ---
EXTENT_ORDER = ["Site-specific", "Community", "Sub-regional", "Regional and broader"]
EXTENT_RADIUS = {
    "Site-specific": 5,
    "Community": 7,
    "Sub-regional": 9,
    "Regional and broader": 11,
}
EXTENT_COLOR = {
    "Site-specific": "#1f6feb",
    "Community": "#10b981",
    "Sub-regional": "#f59e0b",
    "Regional and broader": "#7c3aed",
}

# --- COMMUNITY TYPES ---
COMM_TYPE_FIELD = "Type"  # "RD", "LG" or "FN"
COMM_LINE_COLORS = {
    "RD": "#A9A9A9",
    "LG": "#374151",
    "FN": "#f97316",
}

# --- FILTER FIELDS ---
FILTER_FIELDS = [
    "Does the Study Outcome Aim to Reduce Risk? (Y/N)",
    "Reduce Hazard (Y/N)",
    "Reduce Exposure (Y/N)",
    "Reduce Vulnerability (Y/N)",
    "Build Resilience (Y/N)",
    "Does the Study Outcome Aim to Provide Ecosystem Services? (Y/N)",
    "How Does the Project Outcome Aim to Provide Ecosystem Services?",
]

AIM_FILTER_CHOICES = {
    "reduce_risk": "Reduce Risk",
    "reduce_hazard": "Reduce Hazard",
    "reduce_exposure": "Reduce Exposure",
    "reduce_vulnerability": "Reduce Vulnerability",
    "build_resilience": "Build Resilience",
    "provide_ecosystem_services": "Provide Ecosystem Services",
}

AIM_FILTER_FIELDS = {
    "reduce_risk": "Does the Study Outcome Aim to Reduce Risk? (Y/N)",
    "reduce_hazard": "Reduce Hazard (Y/N)",
    "reduce_exposure": "Reduce Exposure (Y/N)",
    "reduce_vulnerability": "Reduce Vulnerability (Y/N)",
    "build_resilience": "Build Resilience (Y/N)",
    "provide_ecosystem_services": "Does the Study Outcome Aim to Provide Ecosystem Services? (Y/N)",
}

# --- HIDDEN & DEFAULT FIELDS ---
ALWAYS_HIDDEN_FIELD_NAMES = {
    "fid",
    "project id",
    "year of commencement",
    "created by",
    "date created",
    "modified by",
    "date modified",
}

DEFAULT_SELECTED_FIELDS = [
    "Project Name",
    "Project Proponent/Owner",
    "Year of Completion",
    "Project Goals",
    "Most Prominent Hazards",
    "Sendai Priority",
]
