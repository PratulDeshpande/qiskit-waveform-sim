# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.4] - 2026-10-06

### Added
- **TargetWaveformSimulator**: Zero-bloat waveform simulator for Qiskit 2.0+ scheduled circuits
- **Exact Virtual-Z Frame Tracking**: Per-qubit phase accumulation with cross-resonance phase-locking
- **Lazy Windowed Evaluation**: O(W) memory snippet extraction via binary search interval indexing
- **Analytical Envelope Synthesis**: DRAG (with leakage suppression) and GaussianSquare envelopes
- **Fractional Gate Support**: Continuous amplitude/duration scaling for RX(θ), RZZ(θ)
- **PulseEnvelopeAnnotation**: Custom pulse shapes via Qiskit 2.0 BoxOp + Annotation API
- **OpenQASM 3 Serialization**: Round-trip serialization with pulse annotation pragmas
- **QPY Support**: Binary serialization with annotation factories via `as_qpy()`
- **Interactive Visualization**: Plotly-based Pulse Sheet + I/Q Oscilloscope
- **Static Visualization**: Publication-quality Matplotlib plots
- **Hardware Export**: LabOne Q, RFSoC/QICK, generic AWG formats
- Removed broken `compile_unscheduled()` fallback; only scheduled circuits via `compile()` are supported
- **Comprehensive Test Suite**: 52 tests covering core, annotations, integration, visualization

### Changed
- **DRAG Boundary Fix**: Q quadrature now vanishes at boundaries via windowed derivative
- **Delay Unit Conversion**: Proper handling of s/ms/us/ns/ps/dt units
- **Interval Search**: Cached starts + max_duration lookback for long events
- **Silent Drop Prevention**: Warnings for unknown operations
- **NPZ Flattening**: Proper numeric arrays for RFSoC/QICK export

### Fixed
- **README Quickstart**: Removed BoxOp from scheduled path (transpiler incompatible)
- **export_openqasm3**: Default PulseAnnotationSerializer for pulse_sim.envelope
- **show_* return types**: Correct Optional[go.Figure] annotations
- **Hardware Export**: NPZ flattening, CSV filename sanitization
- **QPY Round-trip**: Proper annotation_factories + as_qpy() usage

### Dependencies
- Minimum: qiskit>=1.0.0,<3.0.0, numpy>=1.24, matplotlib>=3.7, plotly>=5.18
- Removed: pydantic (unused)
- Optional: kaleido (static Plotly export)

### Fixed
- **annotations.py**: Fixed Qiskit Annotation import with try/except for 1.x/2.x compatibility
- **CR Phase Tracking**: Cross-resonance drive now uses control qubit frame phase (correct physics)
- **Version Constraint**: Honest qiskit>=1.0.0,<3.0.0 (only qasm3/Annotation are 2.x specific)

### Documentation
- Sphinx documentation with 3 Jupyter tutorials
- API reference for core, annotations, visualization
- Quickstart, installation, contributing guides