from setuptools import setup, find_packages


requirements = [
    "AIOConductor",
    "ConfigTree",
    "Python-RapidJSON",
    "ValidX",
    "cached_property",
    "AIOHTTP",
]

with open("README.rst") as f:
    readme = f.read()

setup(
    name="Myack",
    version="0.1",
    description="Tools for building web services",
    long_description=readme,
    classifiers=[
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: Implementation :: CPython",
        "Framework :: AsyncIO",
    ],
    keywords="asyncio asynchronous web services",
    url="https://bitbucket.org/myack/myack",
    author="Myack Inc.",
    author_email="support@myack.com",
    license="BSD",
    packages=find_packages(exclude=["tests", "tests.*"]),
    package_data={"myack": ["py.typed"]},
    zip_safe=False,
    install_requires=requirements,
)
