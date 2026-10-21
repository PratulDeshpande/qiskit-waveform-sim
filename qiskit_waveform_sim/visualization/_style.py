"""Shared styling for the Plotly and Matplotlib visualizations."""

from __future__ import annotations

from qiskit_waveform_sim.core import ChannelEvent

OP_COLORS = {
    "drag": "#1f77b4",  # Blue for single-qubit drives
    "gaussian_square": "#2ca02c",  # Green for two-qubit cross-resonance
    "virtual_z": "#ff7f0e",  # Orange for virtual Z
    "measure": "#d62728",  # Red for measure
    "ecr_echo_x": "#9467bd",  # Purple for echo
    "default": "#7f7f7f",  # Gray
}


def event_color(ev: ChannelEvent) -> str:
    """Colour for an event: specific operations first, then the pulse shape."""
    return OP_COLORS.get(ev.op_name) or OP_COLORS.get(ev.shape, OP_COLORS["default"])
