from setuptools import find_packages, setup

from pathlib import Path

setup(
    name='mt2gf',
    version='0.1.0',
    author='Yann Mentha',
    author_email="yann.mentha@gmail.com",

    packages = find_packages(),
    license='MIT',
    python_requires='>=3.6',
    install_requires= Path("requirements.txt").read_text().splitlines(),
)
