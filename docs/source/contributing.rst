Contributing to qiskit-waveform-sim
====================================

We welcome contributions! This guide will help you get started.

Code of Conduct
---------------

This project follows our `Code of Conduct <../CODE_OF_CONDUCT.md>`_.
By participating, you agree to uphold this code.

How to Contribute
-----------------

### Reporting Issues

* Search existing issues first to avoid duplicates
* Use the issue templates when available
* Provide minimal reproduction steps
* Include environment info (Python version, Qiskit version, OS)

### Submitting Pull Requests

1. Fork the repository
2. Create a feature branch: ``git checkout -b feature/my-feature``
3. Make your changes
4. Run tests and linters (see below)
5. Submit a PR with a clear description

### Development Setup

.. code-block:: bash

   git clone https://github.com/PratulDeshpande/qiskit-waveform-sim
   cd qiskit-waveform-sim
   pip install -e ".[dev,test,docs]"
   pre-commit install

### Running Tests

.. code-block:: bash

   # Run all tests
   pytest -v tests/

   # Run with coverage
   pytest --cov=qiskit_waveform_sim tests/

   # Run specific test file
   pytest -v tests/test_core.py

   # Run with parallel execution
   pytest -n auto tests/

### Code Style

We use the following tools (configured in ``pyproject.toml``):

* **Ruff** - Fast Python linter
* **Black** - Code formatter
* **MyPy** - Static type checker

Run all checks:

.. code-block:: bash

   ruff check qiskit_waveform_sim tests
   black --check qiskit_waveform_sim tests
   mypy qiskit_waveform_sim

Auto-fix formatting:

.. code-block:: bash

   ruff check --fix qiskit_waveform_sim tests
   black qiskit_waveform_sim tests

### Adding New Features

1. **Core Engine**: Add new envelope types in ``AnalyticalEnvelopes``
2. **Annotations**: Extend ``PulseEnvelopeAnnotation`` for new pulse parameters
3. **Visualization**: Add new Plotly/Matplotlib functions in ``visualization/``
4. **Hardware Export**: Add new export functions in tutorials/examples

### Testing Guidelines

* Write tests for new functionality in ``tests/``
* Use fixtures from ``tests/conftest.py``
* Mark slow tests with ``@pytest.mark.slow``
* Mark integration tests with ``@pytest.mark.integration``

### Documentation

* Update docstrings for public APIs (NumPy style)
* Add examples to relevant tutorial notebooks
* Build docs locally: ``cd docs && sphinx-build -b html source source/_build/html``

### Release Process

Releases are managed by maintainers:

1. Update version in ``pyproject.toml`` and ``qiskit_waveform_sim/__init__.py``
2. Update ``CHANGELOG.md``
3. Create git tag: ``git tag vX.Y.Z``
4. Push tag: ``git push origin vX.Y.Z``
5. GitHub Actions builds and publishes to PyPI

Architecture Decisions
----------------------

Key architectural decisions are documented in the `Idea.md` file and the
`Implementation Plan`. Major changes should reference these documents.

Getting Help
------------

* Open a GitHub Discussion for questions
* Check existing issues and PRs