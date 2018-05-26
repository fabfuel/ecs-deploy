FROM python:3.5-alpine

WORKDIR /root
COPY . /root/ecs_deploy
WORKDIR /root/ecs_deploy
RUN pip install -r requirements.txt
RUN pip install .
