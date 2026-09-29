"""Tricentis Tosca documentation references used by the rules.

Links are built from a version string so they follow the Tosca release the
customer runs. The server can check them at analysis time (see app/docs_check.py).
"""
from __future__ import annotations

DEFAULT_VERSION = "2026.1"
BASE = "https://docs.tricentis.com/tosca-{version}/en-us/content/"

TOPICS: dict[str, tuple[str, str]] = {
    # key: (label shown on the finding, path under BASE)
    "wait_times": ("Wait times", "best_practices/testcases_wait_times.htm"),
    "action_modes": ("ActionModes", "tbox/action_modes.htm"),
    "sync_settings": ("Synchronization settings", "tosca_commander/settings_tbox_synchronization.htm"),
    "rtb": ("Reusable TestStepBlocks", "tosca_commander/reusable_teststepblocks.htm"),
    "libraries": ("TestStepLibraries", "tosca_commander/teststep_libraries.htm"),
    "tcp": ("Test configuration parameters", "tosca_commander/tcp_create_tcp.htm"),
    "dates": ("Dynamic date and time expressions", "tbox/date_and_time_expressions.htm"),
    "recovery": ("Recovery and clean-up scenarios", "tbox/recovery_cleanup.htm"),
    "error_handling": ("Error handling", "best_practices/testcases_error_handling.htm"),
    "content": ("TestCase content", "best_practices/testcases_content.htm"),
    "overview": ("Best practices", "best_practices/best_practices_overview.htm"),
}


def link(topic: str, version: str = DEFAULT_VERSION) -> dict:
    label, path = TOPICS.get(topic, TOPICS["overview"])
    return {"topic": topic, "label": label, "url": BASE.format(version=version) + path}
