Installation
============

Requirements
------------

- **Python**: 3.11 or 3.12
- **Qiskit**: 2.0.0 or later
- **NumPy**: 1.24 or later
- **Matplotlib**: 3.7 or later
- **Plotly**: 5.18 or later

Install from PyPI
-----------------

.. code-block:: bash

   pip install qiskit-waveform-sim

Install with Optional Dependencies
----------------------------------

.. code-block:: bash

   # For development (linting, type checking, testing)
   pip install qiskit-waveform-sim[dev]

   # For running tests
   pip install qiskit-waveform-sim[test]

   # For building documentation
   pip install qiskit-waveform-sim[docs]

   # All optional dependencies
   pip install qiskit-waveform-sim[dev,test,docs]

Install from Source
-------------------

.. code-block:: bash

   git clone https://github.com/Qiskit/qiskit-waveform-sim
   cd qiskit-waveform-sim
   pip install -e ".[dev,test,docs]"

Development Setup
-----------------

.. code-block:: bash

   # Install pre-commit hooks
   pre-commit install

   # Run tests
   pytest -v tests/

   # Run linters
   ruff check qiskit_waveform_sim tests
   black --check qiskit_waveform_sim tests
   mypy qiskit_waveform_sim

   # Build documentation
   cd docs
   sphinx-build -b html source source/_build/html

Verifying Installation
----------------------

.. code-block:: python

   import qiskit_waveform_sim
   print(qiskit_waveform_sim.__version__)
   
   # Test basic import
   from qiskit_waveform_sim import TargetWaveformSimulator, PulseEnvelopeAnnotation
   print("Import successful!")

Troubleshooting
---------------

**Qiskit Version Conflicts**

If you encounter version conflicts, ensure you have Qiskit 2.0+:

.. code-block:: bash

   pip install --upgrade "qiskit>=2.0.0"

**Plotly/Kaleido Issues**

For static image export, install kaleido:

.. code-block:: bash

   pip install kaleido

**Apple Silicon (M1/M2/M3)**

All dependencies have native ARM64 wheels. If you encounter issues:

.. code-block:: bash

   pip install --upgrade pip setuptools wheel
   pip install qiskit-waveform-sim