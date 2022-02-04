from setuptools import setup, find_packages

setup(
    name="SecurityBot",
    version="0.0.1",
    description="The glue between human and security interfaces",
    url="https://github.com/michael-robbins/securitybot",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Topic :: Communications :: Chat",
        "Topic :: Security",
        "Topic :: Home Automation",
    ],
    keywords="slack slackbot zoneminder security",
    license="GNU",
    packages=find_packages(),
    install_requires=[
        "pyyaml>=3,<7",
        "slackclient>=1.1,<3",
    ],
    python_requires="~=3.5",
    extras_require={
        "test": ["pytest>=3.3,<8"],
    }
)
