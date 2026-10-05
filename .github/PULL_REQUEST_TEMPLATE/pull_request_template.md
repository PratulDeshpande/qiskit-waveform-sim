---
name: Pull Request Template
description: Standard PR template for qiskit-waveform-sim
title: "[PR]: "
labels: ["needs-review"]
body:
  - type: markdown
    attributes:
      value: |
        Thanks for contributing! Please fill out the following sections.
  - type: checkboxes
    id: checklist
    attributes:
      label: Checklist
      options:
        - label: I have read the [CONTRIBUTING.md](CONTRIBUTING.md) guidelines
          required: true
        - label: I have run `pytest tests/` locally and all tests pass
          required: true
        - label: I have run `ruff check qiskit_waveform_sim tests` and `black --check qiskit_waveform_sim tests`
          required: true
        - label: I have run `mypy qiskit_waveform_sim` and it passes
          required: true
        - label: I have added/updated tests for my changes
          required: true
        - label: I have updated documentation/docstrings as needed
          required: true
        - label: I have added an entry to CHANGELOG.md (if user-facing)
          required: false
  - type: dropdown
    id: type
    attributes:
      label: Type of Change
      options:
        - Bug fix (non-breaking change fixing an issue)
        - New feature (non-breaking change adding functionality)
        - Breaking change (fix or feature that would cause existing functionality to not work as expected)
        - Documentation update
        - Performance improvement
        - Code refactoring (no functional changes)
        - Test improvement
        - CI/CD improvement
        - Other
    validations:
      required: true
  - type: textarea
    id: description
    attributes:
      label: Description
      description: Describe your changes in detail
      placeholder: What does this PR do? Why is it needed?
    validations:
      required: true
  - type: textarea
    id: motivation
    attributes:
      label: Motivation / Context
      description: Why is this change required? What problem does it solve?
      placeholder: Link to issue, describe the use case, etc.
    validations:
      required: false
  - type: textarea
    id: testing
    attributes:
      label: How Has This Been Tested?
      description: Describe the tests you ran and their results
      placeholder: |
        - Ran `pytest tests/` - all 52 tests pass
        - Added test case in `tests/test_core.py::test_new_feature`
        - Verified with `examples/basic_example.py`
    validations:
      required: true
  - type: textarea
    id: breaking
    attributes:
      label: Breaking Changes
      description: If this is a breaking change, describe the migration path
      placeholder: |
        - Changed `TargetWaveformSimulator.compile()` signature
        - Migration: `compile_unscheduled()` removed; only `compile()` with scheduled circuits supported
    validations:
      required: false
  - type: checkboxes
    id: related
    attributes:
      label: Related Issues / PRs
      options:
        - label: Fixes #(issue number)
        - label: Related to #(issue number)
        - label: Part of #(epic/milestone)
    validations:
      required: false