Changelog
=========

Version 0.1.0 (2026-10-04)
--------------------------

Initial release of qiskit-waveform-sim.

Features
~~~~~~~~

* **TargetWaveformSimulator**: Zero-bloat waveform simulator for Qiskit 2.0+ scheduled circuits
* **Exact Virtual-Z Frame Tracking**: Per-qubit phase accumulation with cross-resonance phase-locking
* **Lazy Windowed Evaluation**: O(W) memory snippet extraction via binary search interval indexing
* **Analytical Envelope Synthesis**: DRAG (with leakage suppression) and GaussianSquare envelopes
* **Fractional Gate Support**: Continuous amplitude/duration scaling for RX(θ), RZZ(θ)
* **PulseEnvelopeAnnotation**: Custom pulse shapes via Qiskit 2.0 BoxOp + Annotation API
* **OpenQASM 3 Serialization**: Round-trip serialization with pulse annotation pragmas
* **QPY Support**: Binary serialization with annotation handlers
* **Interactive Visualization**: Plotly-based Pulse Sheet + I/Q Oscilloscope
* **Static Visualization**: Publication-quality Matplotlib plots
* **Hardware Export**: LabOne Q, RFSoC/QICK, ARTIQ, generic AWG formats

Architecture
~~~~~~~~~~~~

* Designed around Qiskit 2.0 Target, op_start_times, BoxOp, and Annotation APIs
* No dependency on deprecated qiskit.pulse or qiskit-dynamics
* Compatible with GenericBackendV2, FakeBackendV2, and custom Target objects
* Matches LabOne Q OutputSimulator architecture (logical timing + parametric pulses + on-demand synthesis)

Testing
~~~~~~~

* Comprehensive test suite with pytest (unit, integration, visualization)
* Tested against Qiskit 2.0.0
* CI configuration with tox for Python 3.11/3.12

Documentation
~~~~~~~~~~~~~

* Sphinx documentation with MyST parser
* Three Jupyter notebook tutorials (Quickstart, Annotations, Hardware Export)
* Full API reference with autodoc