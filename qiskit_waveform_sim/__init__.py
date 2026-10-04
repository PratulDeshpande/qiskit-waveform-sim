"""
qiskit-waveform-sim: Zero-bloat Classical Control Waveform Simulator & Interactive Pulse Sheet Viewer for Qiskit 2.5+

This package provides a native, offline, lazy-evaluated waveform simulator that works directly
with Qiskit's modern Target, op_start_times, BoxOp, fractional gates, and the new
qiskit.circuit.annotation.Annotation API.
"""

from qiskit_waveform_sim.core import (
    TargetWaveformSimulator,
    WaveformSnippet,
    ChannelEvent,
    AnalyticalEnvelopes,
)
from qiskit_waveform_sim.annotations import (
    PulseEnvelopeAnnotation,
    PulseAnnotationSerializer,
)
from qiskit_waveform_sim.visualization import (
    create_pulse_sheet,
    create_iq_oscilloscope,
    show_pulse_sheet,
    show_iq_oscilloscope,
    create_combined_view,
    PulseSheetConfig,
)

__version__ = "0.1.0"
__all__ = [
    "TargetWaveformSimulator",
    "WaveformSnippet",
    "ChannelEvent",
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