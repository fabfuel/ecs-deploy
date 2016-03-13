"""
Simplify AWS ECS deployments
"""
from setuptools import find_packages, setup

dependencies = ['click', 'botocore', 'boto3', 'future']

setup(
    name='ecs-deploy',
    version='0.1.0',
    url='https://github.com/fabfuel/ecs-deploy',
    license='BSD',
    author='Fabian Fuelling',
    author_email='fabian@fabfuel.de',
    description='Simplify AWS ECS deployments',
    long_description=__doc__,
    packages=find_packages(exclude=['tests']),
    include_package_data=True,
    zip_safe=False,
    platforms='any',
    install_requires=dependencies,
    entry_points={
        'console_scripts': [
            'ecs = ecs_deploy.cli:main',
        ],
    },
    tests_require=[
        'pytest',
        'pytest-flake8',
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
