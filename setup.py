"""
Simplify AWS ECS deployments
"""
from setuptools import find_packages, setup

from ecs_deploy.ecs import VERSION

dependencies = ['click', 'botocore', 'boto3>=1.4.7', 'future', 'requests']

setup(
    name='ecs-deploy',
    version=VERSION,
    url='https://github.com/fabfuel/ecs-deploy',
    download_url='https://github.com/fabfuel/ecs-deploy/archive/%s.tar.gz' % VERSION,
    license='BSD',
    author='Fabian Fuelling',
    author_email='pypi@fabfuel.de',
    description='Simplify Amazon ECS deployments',
    long_description=__doc__,
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
        'coverage'
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
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
