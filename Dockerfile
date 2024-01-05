FROM python:3.10-alpine

ADD . /usr/src/app
WORKDIR /usr/src/app

RUN ["python", "setup.py", "install"]

CMD ["ecs"]
