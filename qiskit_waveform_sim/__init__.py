"""
qiskit-waveform-sim: Control-waveform synthesizer and pulse-schedule viewer for Qiskit 2.x

It turns scheduled Qiskit 2.x circuits into sample-level I/Q control waveforms
with Virtual-Z frame tracking, and draws them as an interactive pulse sheet.
It does not simulate qubit dynamics. It is offline, lazy-evaluated, and works
directly with Qiskit's modern Target, op_start_times, BoxOp, fractional gates,
and the new qiskit.circuit.annotation.Annotation API.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version

from qiskit_waveform_sim.annotations import (
    PulseAnnotationSerializer,
    PulseEnvelopeAnnotation,
)
from qiskit_waveform_sim.core import (
    AnalyticalEnvelopes,
    ChannelEvent,
    PulseDefaults,
    TargetWaveformSimulator,
    WaveformSnippet,
)
from qiskit_waveform_sim.visualization import (
    PulseSheetConfig,
    create_combined_view,
    create_iq_oscilloscope,
    create_pulse_sheet,
    show_iq_oscilloscope,
    show_pulse_sheet,
)

try:
    # Single source of truth: the version declared in pyproject.toml
    __version__ = _package_version("qiskit-waveform-sim")
except PackageNotFoundError:  # pragma: no cover - running from an uninstalled checkout
    __version__ = "0.0.0+unknown"
__all__ = [
    "TargetWaveformSimulator",
    "WaveformSnippet",
    "ChannelEvent",
    "PulseDefaults",
    "AnalyticalEnvelopes",
    "PulseEnvelopeAnnotation",
    "PulseAnnotationSerializer",
    "create_pulse_sheet",
    "create_iq_oscilloscope",
    "show_pulse_sheet",
    "show_iq_oscilloscope",
    "create_combined_view",
    "PulseSheetConfig",
]
