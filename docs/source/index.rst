.. qiskit-waveform-sim documentation master file

Welcome to qiskit-waveform-sim's documentation!
================================================

**qiskit-waveform-sim** is a zero-bloat Classical Control Waveform Simulator & Interactive Pulse Sheet Viewer for Qiskit 2.5+.

It bridges the post-Pulse waveform gap created by Qiskit 2.0-2.5's architectural overhaul, providing:

- **Lazy Windowed Evaluation**: :math:`O(W)` memory for snippet extraction, independent of total circuit depth
- **Exact Virtual-Z Frame Tracking**: Per-qubit phase accumulation propagated to drive and cross-resonance channels
- **Analytical Envelope Synthesis**: DRAG (with leakage suppression), GaussianSquare (flat-top with pedestal correction)
- **Fractional Gate Support**: Continuous parametric amplitude/duration scaling for :math:`R_X(\theta)`, :math:`R_{ZZ}(\theta)`
- **BoxOp & Annotation Native**: Custom ``PulseEnvelopeAnnotation`` with OpenQASM 3 & QPY serialization
- **Interactive Visualization**: Plotly-based Pulse Sheet + synchronized I/Q Oscilloscope
- **LabOne Q Compatible Architecture**: ``OutputSimulator.get_snippet()``-style API

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