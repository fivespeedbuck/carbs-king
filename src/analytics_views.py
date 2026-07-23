"""Compatibility exports for the modular analytics feature.

New code should import models from :mod:`analytics_model` and page composition
from :mod:`analytics_page`.  This facade keeps the established public API
stable for callers while the feature owns a single implementation.
"""

from analytics_model import CHART_OPTIONS, DataPageConfig, build_data_page_model
from analytics_page import build_data_page_view, build_main_data_page_hook

__all__ = [
    "CHART_OPTIONS",
    "DataPageConfig",
    "build_data_page_model",
    "build_data_page_view",
    "build_main_data_page_hook",
]
