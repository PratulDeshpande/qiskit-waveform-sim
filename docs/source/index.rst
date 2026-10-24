.. qiskit-waveform-sim documentation master file

Welcome to qiskit-waveform-sim's documentation!
================================================

**qiskit-waveform-sim** is a control-waveform synthesizer and pulse-schedule viewer for Qiskit 2.x. Turns scheduled Qiskit 2.x circuits into sample-level I/Q control waveforms with Virtual-Z frame tracking, and draws them as an interactive pulse sheet. It does not simulate qubit dynamics.

It bridges the post-Pulse waveform gap created by Qiskit 2.0-2.5's architectural overhaul, providing:

- **Lazy Windowed Evaluation**: :math:`O(W)` memory for snippet extraction, independent of total circuit depth
- **Virtual-Z Frame Tracking**: Per-qubit phase accumulation propagated to drive and cross-resonance channels
- **Analytical Envelope Synthesis**: DRAG (with leakage suppression), GaussianSquare (flat-top with pedestal correction)
- **Fractional Gate Support**: Amplitude scaling for :math:`R_X(\theta)`, :math:`R_{ZZ}(\theta)` (angles wrapped to :math:`[-\pi, \pi]`)
- **BoxOp & Annotation Native**: Custom ``PulseEnvelopeAnnotation`` with OpenQASM 3 & QPY serialization, applied whenever the circuit carries start times
- **Interactive Visualization**: Plotly-based Pulse Sheet + synchronized I/Q Oscilloscope
- **get_snippet() windowed API** (inspired by LabOne Q's OutputSimulator)

.. note::
   **Analytical Envelope Philosophy**: ``qiskit-waveform-sim`` is designed for offline, deterministic control-waveform synthesis. Rather than querying cloud-based calibration databases over the network, it synthesizes standardized, idealized physical pulse envelopes (such as DRAG with derivative leakage suppression and GaussianSquare with flat-top rise/fall pedestal corrections) derived directly from circuit gate names, parameters, and modern ``Target`` instruction durations.

.. admonition:: Scope and limitations

   - It synthesizes the waveforms a controller would play; it does **not** evolve a qubit Hamiltonian.
   - Amplitudes are uncalibrated placeholders, a fraction of DAC full scale. Override them with ``PulseDefaults`` or per-box ``PulseEnvelopeAnnotation``.
   - Qiskit's scheduler rejects ``BoxOp``, so pass ``compile(qc, start_times=[...])`` for boxed circuits.
   - Roadmap: an optional QuTiP-based dynamics bridge.

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   quickstart
   installation

.. toctree::
   :maxdepth: 2
   :caption: Tutorials

   tutorials/quickstart
   tutorials/annotations
   tutorials/hardware_export

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/core
   api/annotations
   api/visualization

.. toctree::
   :maxdepth: 1
   :caption: Additional Resources

   changelog
   contributing
   license

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`