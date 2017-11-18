# -*- coding: utf-8 -*-
from __future__ import print_function

import sys, re
sys.path.append('Python-Thermal-Printer')
from Adafruit_Thermal import *
import json
from time import time, sleep
from datetime import datetime, timedelta
from threading import Thread
from queue import Queue
from twython import TwythonStreamer
from twilio.rest import Client
import pytz
from unidecode import unidecode

utc=pytz.UTC

class TwitterStreamReceiver(TwythonStreamer):
    def __init__(self, *args, **kwargs):
        super(TwitterStreamReceiver, self).__init__(*args, **kwargs)
        self.tweetQ = Queue()
    def on_success(self, data):
        if ('text' in data):
            self.tweetQ.put(data['text'].encode('utf-8'))
            print("received %s" % (data['text']))
    def on_error(self, status_code, data):
        print("ERROR:", status_code)
    def empty(self):
        return self.tweetQ.empty()
    def get(self):
        return self.tweetQ.get()

def setup():
    global lastTwitterCheck, myTwitterStream, streamThread
    global lastSmsCheck, mySmsClient, newestSmsSeconds
    global PHONE_NUMBER
    global logFile
    lastTwitterCheck = time()
    lastSmsCheck = time()
    newestSmsSeconds = datetime.now(utc)

    printer = Adafruit_Thermal("/dev/tty.usbserial", 9600, timeout=5)
    printer.begin(255)

    with open('secrets.json') as dataFile:
        data = json.load(dataFile)
        ## What to search for
    SEARCH_TERMS = data["search_terms"]
    PHONE_NUMBER = data["phone_number"]

    ## start Twitter stream reader
    myTwitterStream = TwitterStreamReceiver(app_key = data["twitter"]['CONSUMER_KEY'],
                                            app_secret = data["twitter"]['CONSUMER_SECRET'],
                                            oauth_token = data["twitter"]['ACCESS_TOKEN'],
                                            oauth_token_secret = data["twitter"]['ACCESS_SECRET'])
    streamThread = Thread(target=myTwitterStream.statuses.filter, kwargs={'track':','.join(SEARCH_TERMS)})
    streamThread.daemon = True
    streamThread.start()
    ## start Twilio client
    mySmsClient = Client(data["twilio"]['ACCOUNT_SID'], data["twilio"]['AUTH_TOKEN'])

    ## open new file for writing log
    now = datetime.now(utc)
    logFile = open("logs/" + now.isoformat() + ".log", "a")

def cleanTagAndSendText(text):
    ## removes punctuation
    # text = re.sub(r'[.,;:!?*/+=\-&%^/\\_$~()<>{}\[\]]', ' ', text)
    ## replaces double-spaces with single space
    # text = re.sub(r'( +)', ' ', text)

    ## log
    now = datetime.now(utc)
    logFile.write(now.isoformat() + "  ***  "+ text +"\n")
    logFile.flush()


def loop():
    global lastTwitterCheck, myTwitterStream, streamThread
    global lastSmsCheck, mySmsClient, newestSmsSeconds
    ## check twitter queue
    if((time()-lastTwitterCheck > 5) and (not myTwitterStream.empty())):
        tweet = myTwitterStream.get().lower()
        tweet = tweet.decode('utf-8')
        ## removes re-tweet
        tweet = re.sub(r'(^[rR][tT] )', '', tweet)
        ## removes hashtags, arrobas and links
        tweet = re.sub(r'(#\S+)|(@\S+)|(http://\S+)', '', tweet)
        ## clean, tag and send text
        cleanTagAndSendText(tweet)
        lastTwitterCheck = time()

    ## check sms
    if(time()-lastSmsCheck > 2):
        print("Checking sms %s", time())
        smss = mySmsClient.messages.list(to=PHONE_NUMBER, date_sent_after = newestSmsSeconds)
        for sms in smss:
            smsSeconds = sms.date_sent
            if (smsSeconds > newestSmsSeconds):
                newestSmsSeconds = smsSeconds
            print("sms: %s" % (sms.body))
            body = sms.body
            mySmsClient.api.account.messages.create(
                to=sms.from_,
                from_=sms.to,
                body="Hello, Got your message thanks")
            sms.delete()
            ## clean, tag and send text
            cleanTagAndSendText(body)
        lastSmsCheck = time()

if __name__=="__main__":
    setup()

    try:
        while(True):
            ## keep it from looping faster than ~60 times per second
            loopStart = time()
            loop()
            loopTime = time()-loopStart
            if (loopTime < 0.016):
                sleep(0.016 - loopTime)
    except KeyboardInterrupt :
        logFile.close()
        myTwitterStream.disconnect()
        sys.exit(0)
