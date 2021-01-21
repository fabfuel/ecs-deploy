"""
Simplify AWS ECS deployments
"""
from setuptools import find_packages, setup

from ecs_deploy import VERSION


def readme():
    with open('README.rst') as f:
        return f.read()


dependencies = ['click<7.0.0', 'botocore>=1.17.47', 'boto3>=1.14.47', 'future', 'requests', 'dictdiffer==0.8.0']

setup(
    name='ecs-deploy',
    version=VERSION,
    url='https://github.com/fabfuel/ecs-deploy',
    download_url='https://github.com/fabfuel/ecs-deploy/archive/%s.tar.gz' % VERSION,
    license='BSD-3-Clause',
    author='Fabian Fuelling',
    author_email='pypi@fabfuel.de',
    description='Powerful CLI tool to simplify Amazon ECS deployments, '
                'rollbacks & scaling',
    long_description=readme(),
    packages=find_packages(exclude=['tests']),
    include_package_data=True,
    zip_safe=False,
    platforms='any',
    install_requires=dependencies,
    entry_points={
        'console_scripts': [
            'ecs = ecs_deploy.cli:ecs',
        ],
    },
    tests_require=[
        'mock',
        'pytest',
        'pytest-flake8',
        'pytest-mock',
        'freezegun',
        'coverage'
    ],
    classifiers=[
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: POSIX',
        'Operating System :: MacOS',
        'Operating System :: Unix',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ]
)
