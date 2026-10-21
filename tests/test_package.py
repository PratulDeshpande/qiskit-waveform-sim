"""
Tests for package metadata.
"""

from importlib.metadata import version

import qiskit_waveform_sim


def test_version_matches_metadata():
    """__version__ is read from the installed distribution (pyproject.toml)."""
    assert qiskit_waveform_sim.__version__ == version("qiskit-waveform-sim")
