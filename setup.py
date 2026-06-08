"""
Simplify AWS ECS deployments
"""
from pathlib import Path
from setuptools import find_packages, setup

from ecs_deploy import VERSION

BASE_DIR = Path(__file__).parent


def readme():
    with open(BASE_DIR / 'README.rst') as f:
        return f.read()


def requirements():
    with open(BASE_DIR / 'requirements.txt') as f:
        return [
            line.strip()
            for line in f
            if line.strip() and not line.startswith('#')
        ]


setup(
    name='ecs-deploy',
    version=VERSION,
    url='https://github.com/fabfuel/ecs-deploy',
    download_url='https://github.com/fabfuel/ecs-deploy/archive/%s.tar.gz' % VERSION,
    license='BSD-3-Clause',
    author='Fabian Fuelling',
    author_email='pypi@fabfuel.de',
    description='Powerful CLI tool to simplify Amazon ECS deployments, rollbacks & scaling',
    long_description=readme(),
    long_description_content_type='text/x-rst',
    packages=find_packages(exclude=['tests']),
    include_package_data=True,
    install_requires=requirements(),
    zip_safe=False,
    platforms='any',
    entry_points={
        'console_scripts': [
            'ecs = ecs_deploy.cli:ecs',
        ],
    },
    classifiers=[
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Operating System :: POSIX',
        'Operating System :: MacOS',
        'Operating System :: Unix',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
    ]
)
