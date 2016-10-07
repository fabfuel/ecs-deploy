ECS Deploy
----------

.. image:: https://travis-ci.org/fabfuel/ecs-deploy.svg?branch=develop
    :target: https://travis-ci.org/fabfuel/ecs-deploy

.. image:: https://scrutinizer-ci.com/g/fabfuel/ecs-deploy/badges/coverage.png?b=develop
    :target: https://scrutinizer-ci.com/g/fabfuel/ecs-deploy

.. image:: https://scrutinizer-ci.com/g/fabfuel/ecs-deploy/badges/quality-score.png?b=develop
    :target: https://scrutinizer-ci.com/g/fabfuel/ecs-deploy


Redeploying a service in Amazon ECS causes some effort, even if you just want to pull the most recent image versions.
You have to create a new revision of the task definition and update the service to use the newly created revision. 

This project simplyfies deployments on Amazon ECS by providing a convinience CLI tool for actions, which are executed
pretty often.

TL;DR
-----
Redeploy or scale a service in Amazon ECS as simple as this::

    $ ecs deploy my-cluster my-service --tag latest
    $ ecs scale my-cluster my-service 4


Installation
------------

The project is availably on PyPI. Simply run::

    $ pip install ecs-deploy


Configuration
-------------
As **ecs-deploy** is based on boto3 (the official AWS Python library), there are several ways to configure and store the 
authentication credentials. Please read the boto3 documentation for more details 
(http://boto3.readthedocs.org/en/latest/guide/configuration.html#configuration). The simplest way is by running::

    $ aws configure

Alternatively you can pass the AWS credentials (via `--access-key-id` and `--secret-access-key`) or the AWS
configuration profile (via `--profile`) as options when you run `ecs`. 

Actions
-------
Currently the following actions are supported:

deploy
======
Redeploy a service either without any modifications or with a new image, environment variable and/or command definition.

scale
=====
Scale a service up or down and change the number of running tasks.

run
===
Run a one-off task based on an existing task-definition and optionally override command and/or environment variables.


Usage
-----

For detailed information about the available actions, arguments and options, run::

    $ ecs deploy --help
    $ ecs scale --help

Examples
--------
All examples assume, that authentication has already been configured.  

Simple Redeploy
===============
To redeploy a service without any modifications, but pulling the most recent image versions, run the follwing command.
This will duplicate the current task definition and cause the service to redeploy all running tasks.::

    $ ecs deploy my-cluster my-service
   

Deploy a new tag
================
To change the tag for **all** images in **all** containers in the task definition, run the following command::

    $ ecs deploy my-cluster my-service -t 1.2.3


Deploy a new image
==================
To change the image of a specific container, run the following command::

    $ ecs deploy my-cluster my-service --image webserver nginx:latest
     
This will modify the **webserver** container only and change its image to "nginx:latest".


Deploy several new images
=========================
The `-i` or `--image` option can also be passed several times::

    $ ecs deploy my-cluster my-service -i webserver nginx:1.9 -i application django:latest
     
This will change the **webserver**'s container image to "nginx:1.9" and the **application**'s image to "django:latest".


Set an environment variable
===========================
To add a new or adjust an existing environment variable of a specific container, run the following command::

    $ ecs deploy my-cluster my-service -e webserver SOME_VARIABLE SOME_VALUE
     
This will modify the **webserver** container definition and add or overwrite the environment variable `SOME_VARIABLE` with the value "SOME_VALUE". This way you can add new or adjust already existing environment variables.


Adjust multiple environment variables
=====================================
You can add or change multiple environment variables at once, by adding the `-e` (or `--env`) options several times::

    $ ecs deploy my-cluster my-service -e webserver SOME_VARIABLE SOME_VALUE -e webserver OTHER_VARIABLE OTHER_VALUE -e app APP_VARIABLE APP_VALUE

This will modify the definition **of two containers**.
The **webserver**'s environment variable `SOME_VARIABLE` will be set to "SOME_VALUE" and the variable `OTHER_VARIABLE` to "OTHER_VALUE".
The **app**'s environment variable `APP_VARIABLE` will be set to "APP_VALUE".


Modify a command
================
To change the command of a specific container, run the following command::

    $ ecs deploy my-cluster my-service --command webserver "nginx"

This will modify the **webserver** container and change its command to "nginx".

Scale a service
===============
To change the number of running tasks and scale a service up and down, run this command::

    $ ecs scale my-cluster my-service 4


Run a one-off task
==================
To run a one-off task, based on an existing task-definition, run this command::

    $ ecs run my-cluster my-task

You can define just the task family (e.g. ``my-task``) or you can run a specific revision of the task-definition (e.g.
``my-task:123``). And optionally you can add or adjust environment variables like this::

    $ ecs run my-cluster my-task:123 -e my-container MY_VARIABLE "my value"


Run a task with a custom command
================================

You can override the command definition via option ``-c`` or ``--command`` followed by the container name and the
command in a natural syntax, e.g. no conversion to comma-separation required::

    $ ecs run my-cluster my-task -c my-container "python some-script.py param1 param2"


