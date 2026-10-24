# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-10-24

### Fixed
- **Measure frame phase**: the phase trace of a measure channel now reports the measure frame (0) instead of the drive frame.
- **`get_snippet` channels**: malformed channel names and out-of-range qubits raise `ValueError` instead of silently using qubit 0.
- **Annotated `rx(θ)`**: the annotation amplitude is now scaled by θ/π.
- **Zero-width envelopes**: `AnalyticalEnvelopes.drag` and `gaussian_square` return zeros for zero-width pulses, and `drag` rejects `sigma_dt <= 0`.

### Added
- **`PulseDefaults`**: configurable, documented placeholder amplitudes.
- **`compile(..., start_times=)`**: explicit operation start times instead of a private attribute.
- A warning when the `Target` has no `dt`.
- **CI**: a coverage gate (88%), tutorial notebooks executed with nbmake (added to the `test` extra), and examples smoke-run headless with a job timeout of 20 minutes.

### Changed
- **Breaking (0.x)**: `get_snippet` raises on invalid channels, and annotated `rx` amplitudes change (see Fixed).
- The package is described as a control-waveform synthesizer and pulse-schedule viewer; the plot title is now "Pulse Sheet" and the README gains a "Scope and limitations" section.

### Release history notes
- Tags v0.1.0, v0.1.3 and v0.1.5 were never published to PyPI.
- v0.1.4 and v0.1.5 point to commits that are not on `main` (`main` was rewritten at v0.1.6).
- The v0.2.0 merge commit was recreated (`12556ad` -> `b870f05`) before tagging.
- From 0.3.0 on, tags always point at the merge commit on `origin/main`, and `main` is never force-pushed.

## [0.2.0] - 2026-10-22

### Fixed
- **Pulse sheet phase markers**: Virtual-Z markers are now drawn (Plotly and Matplotlib) and honour `show_phase_markers`.
- **Event colours**: measure pulses render red and ECR echo pulses purple, as the legend says.
- **`create_combined_view`** no longer overwrites the caller's `PulseSheetConfig`.
- **`plot_iq_waveforms`** accepts arrays/lists of axes without mutating them and raises `ValueError` when given too few.
- **Cross-resonance frame**: `u(c,t)` pulses now use the target qubit's frame, consistent with the reported phase trace.
- **Fractional gates**: `rx`/`rzz` angles are wrapped to [-π, π]; over-range `rzz` amplitudes are clipped with a warning instead of aborting `compile()`; unbound parameters raise a clear `ValueError`.
- **Snippet windows**: the last frame phase holds past the circuit end; pulses ending exactly at a window start are no longer reported.
- **BoxOp lowering**: instructions on different qubits run in parallel; a fixed-duration box around one gate sets that gate's duration; boxes without a duration no longer fall back to 160 dt with an "Unknown operation" warning; annotations also apply to `cx`/`ecr`/`rzz`/`cz`.
- **Documentation accuracy**: DRAG docstring sign and edge behaviour (the 0.1.7 note that Q "vanishes at boundaries" was inaccurate: Q is +β·g′, small but non-zero at the edges), real `@pulse_sim.envelope {...}` OpenQASM 3 format, BoxOp scheduling limitation, and tutorials re-executed so their outputs match the code.

### Added
- `cz` gates are drawn as an uncalibrated flat-top pulse on `u(c,t)`.
- A `UserWarning` for gates that occupy time but have no waveform model (e.g. `swap`).
- `PulseEnvelopeAnnotation` validates `amp` (within ±1), `sigma_ratio` (> 0 for drag) and `risefall_dt` (≥ 0).
- `.pre-commit-config.yaml` running ruff, black and mypy.

### Changed
- `__version__` and the docs release are read from package metadata; `pyproject.toml` is the single place to bump the version.
- Docs extra requires `qiskit-sphinx-theme>=2.1` and `sphinx>=9.0.4,<10` (theme 2.0.x needs `sphinx<9`); the docs theme switched from sphinx-rtd-theme to the Qiskit Ecosystem theme.
- CI lints `examples/` and tests both the oldest supported and the newest Qiskit 2.x; tox adds Python 3.13.
- Removed compiled `.pyc` files and a stale test copy from the repository.

## [0.1.8] - 2026-10-12

### Changed
- **Qiskit Ecosystem Compliance ([Q03])**: Added `<3` major version upper-bound cap to Qiskit dependency (`qiskit>=2.5.0,<3`) in `pyproject.toml`.
- **PEP 639 License Specification**: Updated build system to require `setuptools>=77.0`, declared SPDX expression `license = "Apache-2.0"`, specified `license-files = ["LICENSE"]`, and removed superseded Trove license classifier.
- **CI Test Matrix**: Added Python 3.13 to GitHub Actions test matrix in parity with Qiskit Ecosystem validation.
- **Documentation**: Modernized Sphinx intersphinx configuration and synchronized documentation release metadata.

## [0.1.7] - 2026-10-06

### Added
- **TargetWaveformSimulator**: Zero-bloat waveform synthesizer for Qiskit 2.0+ scheduled circuits
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
- Minimum: qiskit>=2.5.0,<3.0.0, numpy>=1.24, matplotlib>=3.7, plotly>=5.18
- Removed: pydantic (unused)
- Optional: kaleido (static Plotly export)

### Documentation
- Sphinx documentation with 3 Jupyter tutorials
- API reference for core, annotations, visualization
- Quickstart, installation, contributing guides