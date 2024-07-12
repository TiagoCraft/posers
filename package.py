name = uuid = 'share'
version = '1.0.0'
description = "FOSS utils."
authors = ["Tiago Craft"]
# Because of the bundled nature of this package, it's dependency on Maya and
# PySide2 was left undeclared. It assumes each part will be used in the proper
# context, instead of forcing such dependencies on the entire package.
requires = []
variants = []
# hashed_variants = True
tests = {
    'import_all_py': {
        'command': 'python {root}/tests/import_all_py.py',
        'run_on': ['default', 'pre_install']
    },
    'import_all_ma': {
        'command': 'mayapy {root}/tests/import_all_ma.py',
        'requires': ['maya'],
        'run_on': ['default', 'pre_install']
    }
}
build_command = 'python {root}/rezbuild.py {install}'


def commands():
    env.PYTHONPATH.append('{root}/python')
    alias('{this.name}_docs',
          expandvars('gio open {root}/docs/build/index.html'))

    alias('{this.name}_makedocs',
          'rez env {this.name}-{this.version} Sphinx -- '
          'sphinx-apidoc -f -e -o {root}/docs/source/ {root}/python/;'
          'rez env {this.name}-{this.version} Sphinx '
          'sphinx_rtd_theme sphinx_autodoc_napoleon_typehints -- '
          'sphinx-build -b html {root}/docs/source/ {root}/docs/build/')
