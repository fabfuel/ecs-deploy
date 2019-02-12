FROM python:3-stretch

RUN pip install --upgrade pip && \
  pip install -e git+https://github.com/fabfuel/ecs-deploy.git@master#egg=ecs-deploy
