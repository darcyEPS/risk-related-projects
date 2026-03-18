"""Risk-Related Projects Dashboard - Main App

Points (500 m snap-to-centroid) + Community (RD/LG/FN) + Legend toggles + Information
- 500 m snap-to-centroid (deterministic; no jitter/offset UI)
- Halo highlight of clicked set (clears/replaced on next click)
- Legend: extent buckets with in-view counts + RD/LG/FN line toggles
- Data tab: All rows (no in-view option)
- No auto-fit on filter changes; initial re-zoom minimized
- Information tab: loaded from information.md file + optional logos
"""

from pathlib import Path
from shiny import App
from ui import app_ui
from server import server

www_dir = Path(__file__).parent / "www"
app = App(app_ui, server, static_assets=www_dir)
