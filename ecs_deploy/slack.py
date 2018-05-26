import requests
from os import getenv
from slacker import Slacker

class SlackException(Exception):
    pass


class SlackDeploymentException(SlackException):
    pass


class SlackLogger(object):
    SLACK_ENDPOINT = getenv('SLACK_ENDPOINT')

    def __init__(self):
        self.slack = Slacker(getenv('SLACK_TOKEN'))
        self.channel = getenv('SLACK_CHANNEL', "test")
        self.first_post = None

    def progress_bar(self, running, pending, desired):
        progress = round(float(running) * 100 / float(desired) / 5)
        pending = round(float(pending) * 100 / float(desired) / 5)
        return (progress * chr(9608)) + (pending * chr(9618)) + ((20 - progress - pending) * chr(9617))

    def post_to_slack(self, message, attachments):
      if self.first_post == None:
          res = self.slack.chat.post_message(self.channel, text=message, attachments=attachments, as_user=True)
          self.first_post = res.body
      else:
          res = self.slack.chat.update(self.first_post['channel'], text=message, attachments=attachments, as_user=True, ts=self.first_post['ts'])
          res.body


    def get_deploy_start_payload(self, service, task_definition):
        #import pdb;pdb.set_trace()
        return "Deploying service %s on cluster %s \nImage: %s" % (service.name, service.cluster, ",".join( [c['image'] for c in task_definition.containers]) )

    def get_deploy_progress_payload(self, service, task_definition):
        primary = [dep for dep in service['deployments'] if dep['status']=='PRIMARY'][0]
        run = primary['runningCount']
        pend = primary['pendingCount']
        des = primary['desiredCount']
        primary_message = {
        "title": "PRIMARY",
        "text": self.progress_bar(run, pend, des) + "\tRunning: %s Pending: %s  Desired: %s" % (run, pend, des)
        }
        attachments = [primary_message]

        active = [dep for dep in service['deployments'] if dep['status']=='ACTIVE']
        for act in active:
            run = act['runningCount']
            pend = act['pendingCount']
            des = act['desiredCount']

            attachments.append({
              "title": "ACTIVE",
              "text": self.progress_bar(run, pend, des) + "\tRunning: %s Pending: %s  Desired: %s" % (run, pend, des)
            })

        messg = self.get_deploy_start_payload(service, task_definition)
        return messg, attachments

    def get_deploy_finish_payload(self, service, task_definition):
        primary = [dep for dep in service['deployments'] if dep['status']=='PRIMARY'][0]
        run = primary['runningCount']
        pend = primary['pendingCount']
        des = primary['desiredCount']
        primary_message = {
        "title": "PRIMARY",
        "text": self.progress_bar(run, pend, des) + "\tRunning: %s Pending: %s  Desired: %s" % (run, pend, des)
        }
        attachments = [primary_message]

        messg = "Deploy finished for service %s on cluster %s\nImage: %s" % (service.name, service.cluster, ",".join( [c['image'] for c in task_definition.containers]))
        return messg, attachments

    def log_deploy_start(self, service, task_definition):
        message = self.get_deploy_start_payload(service, task_definition)
        self.post_to_slack(message, None)


    def log_deploy_progress(self, service, task_definition):
        message, attachments = self.get_deploy_progress_payload(service, task_definition)
        self.post_to_slack(message, attachments)


    def log_deploy_finish(self, service, task_definition):
        message, attachments = self.get_deploy_finish_payload(service, task_definition)
        self.post_to_slack(message, attachments)
