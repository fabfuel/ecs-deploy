FROM python:3.8-alpine3.13

ADD . /usr/src/app
WORKDIR /usr/src/app

RUN ["python", "setup.py", "install"]

CMD ["ecs"]
