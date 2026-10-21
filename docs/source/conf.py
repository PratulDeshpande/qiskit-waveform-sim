# Configuration file for the Sphinx documentation builder.

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _package_version

# -- Project information -----------------------------------------------------
project = 'qiskit-waveform-sim'
copyright = '2026, Pratul Deshpande'
author = 'Pratul Deshpande'
try:
    # Read from the installed package so docs never drift from pyproject.toml
    release = _package_version('qiskit-waveform-sim')
except PackageNotFoundError:
    release = '0.0.0+unknown'
version = release

# -- General configuration ---------------------------------------------------
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
    'sphinx.ext.mathjax',
    'sphinx.ext.viewcode',
    'myst_parser',
    'nbsphinx',
    'qiskit_sphinx_theme',
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store', '**.ipynb_checkpoints']

# -- Options for HTML output -------------------------------------------------
html_theme = 'qiskit-ecosystem'
html_static_path = ['_static']
html_title = f'{project} v{version}'

html_theme_options = {
    "sidebar_qiskit_ecosystem_member": True,
}

# -- Napoleon settings -------------------------------------------------------
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = True

# -- Intersphinx mapping -----------------------------------------------------
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'numpy': ('https://numpy.org/doc/stable/', None),
    'plotly': ('https://plotly.com/python-api-reference/', None),
}

# -- Autosummary -------------------------------------------------------------
autosummary_generate = True
autodoc_default_options = {
    'members': True,
    'undoc-members': True,
    'show-inheritance': True,
}

# -- MyST parser -------------------------------------------------------------
myst_enable_extensions = [
    'colon_fence',
    'deflist',
    'dollarmath',
    'amsmath',
]

# -- nbsphinx ----------------------------------------------------------------
nbsphinx_execute = 'never'  # Don't execute notebooks during build
nbsphinx_allow_errors = True

# -- MathJax ---------------------------------------------------------------
mathjax3_config = {
    'tex': {
        'inlineMath': [['$', '$'], ['\\(', '\\)']],
        'displayMath': [['$$', '$$'], ['\\[', '\\]']],
    }
}
