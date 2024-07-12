import datetime
import os

# -- Project information -----------------------------------------------------
project = __file__.rsplit(os.path.sep, 5)[1]
author = 'Tiago Beijoco'
copyright = f'{datetime.datetime.now().year}, {author}'
version = os.environ[f'REZ_{project.upper()}_VERSION']


# -- General configuration ---------------------------------------------------
extensions = [
    # 'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.intersphinx',
    'sphinx.ext.napoleon',
    'sphinx_autodoc_napoleon_typehints',
    'sphinx.ext.viewcode',
]


# -- Options for HTML output -------------------------------------------------
html_theme = 'sphinx_rtd_theme'
html_sidebars = {
    '**': [
        'searchbox.html',
    ]
}


# -- Extension configuration -------------------------------------------------
autodoc_default_options = {
    'exclude-members': '__weakref__, __dict__, __module__, __annotations__ ',
    'member-order': 'bysource',
    'members': None,
    'special-members': None,
    'undoc-members': True,
    'show-inheritance': True,
}
autosummary_generate = True
napoleon_google_docstring = True
intersphinx_mapping = {'https://docs.python.org/3/': None}
