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
from subprocess32 import TimeoutExpired, check_output, STDOUT, PIPE, Popen
import pygame
from pygame.locals import *
from enum import Enum
from utils import *

utc=pytz.UTC

SCREEN_RESOLUTION = (800, 480)
FONT_SIZE = 20

class TwitterStreamReceiver(TwythonStreamer):
    def __init__(self, *args, **kwargs):
        super(TwitterStreamReceiver, self).__init__(*args, **kwargs)
        self.tweetQ = Queue()
    def on_success(self, data):
        if ('text' in data):
            self.tweetQ.put(data['text'])
            print("received %s" % (data['text']))
    def on_error(self, status_code, data):
        print("ERROR:", status_code)
    def empty(self):
        return self.tweetQ.empty()
    def get(self):
        return self.tweetQ.get()

class SMSReceiver():
    def __init__(self, account_sid, auth_token):
        self.smsClient = Client(account_sid, auth_token)
        self.smsQ = Queue()
        self.lastTime = time()
        self.newestSmsSeconds = datetime.now(utc)
    def update(self):
        while(True):
            if(time() - self.lastTime > 1):
                smss = self.smsClient.messages.list(to=PHONE_NUMBER, date_sent_after = self.newestSmsSeconds)
                for sms in smss:
                    smsSeconds = sms.date_sent
                    if (smsSeconds > self.newestSmsSeconds):
                        self.newestSmsSeconds = smsSeconds
                    body = sms.body
                    print(body)
                    self.smsQ.put(body)
                    sms.delete()

                    # mySmsClient.api.account.messages.create(
                    #     to=sms.from_,
                    #     from_=sms.to,
                    #     body="Hello, Got your message thanks")
                self.lastTime = time()
    def empty(self):
        return self.smsQ.empty()
    def get(self):
        return self.smsQ.get()

class NeuralNetProcessor():
        def __init__(self):
            self.cmd = ['python', 'sample.py', '--init_dir', 'pretrained_shakespeare', '--length', '500', '--start_text']
            self.cwd ='./tensorflow-char-rnn'
            self.isProcessing = False
            self.lastOutput =  unicode('', 'utf8')
            self.start_text = None

        def start(self, start_text):
            self.start_text = start_text
            self.isProcessing = True
            pThread = Thread(target=self.getResult)
            pThread.setName('NeuraProessorThread')
            pThread.start()

        def getResult(self):
            p = Popen(self.cmd + [self.start_text], cwd=self.cwd, stdout=PIPE, stderr=PIPE, shell=False)
            out, err = p.communicate()
            self.isProcessing = False
            self.lastOutput = out

            # try:
            #     print("Start Tread")
            #     outs = check_output(self.cmd, cwd=self.cwd, stdout=PIPE, stderr=STDOUT, timeout=60)
            #     print("End Tread")
            #
            #     self.lastOutput = outs
            #     print(self.lastOutput)
            #     self.isProcessing = False
            # except TimeoutExpired:
            #     logFile.write("Command timed out --- tensorflow problem")
            #     print('ERROR processing tensorflow')


def setup():
    global myTwitterStream, mySmsStream
    global lastTwitterCheck, lastSmsCheck
    global myNeuralNet
    global PHONE_NUMBER
    global logFile
    global screen, font
    global printer
    lastTwitterCheck = time()
    lastSmsCheck = time()

    with open('secrets.json') as dataFile:
        data = json.load(dataFile)
        ## What to search for
    SEARCH_TERMS = data["search_terms"]
    PHONE_NUMBER = data["phone_number"]

    try:
        printer = Adafruit_Thermal(data["usb_port"], 9600, timeout=5)
        printer.begin(255)
    except:
        print('Error loading serial port...')

    ## start Twitter stream reader
    myTwitterStream = TwitterStreamReceiver(app_key = data["twitter"]['CONSUMER_KEY'],
                                            app_secret = data["twitter"]['CONSUMER_SECRET'],
                                            oauth_token = data["twitter"]['ACCESS_TOKEN'],
                                            oauth_token_secret = data["twitter"]['ACCESS_SECRET'])
    streamThread = Thread(target=myTwitterStream.statuses.filter, kwargs={'track':','.join(SEARCH_TERMS)})
    streamThread.daemon = True
    streamThread.setName('TwitterThread')
    streamThread.start()
    ## start Twilio client
    mySmsStream =  SMSReceiver(data["twilio"]['ACCOUNT_SID'], data["twilio"]['AUTH_TOKEN'])
    smsStreamThread = Thread(target=mySmsStream.update)
    smsStreamThread.daemon = True
    smsStreamThread.setName('SmsThread')
    smsStreamThread.start()

    myNeuralNet = NeuralNetProcessor()

    ## open new file for writing log
    now = datetime.now(utc)
    logFile = open("logs/" + now.isoformat() + ".log", "a")
    #getNeuralNetText('Life is hard')

    #init pygame
    pygame.init()
    pygame.display.set_caption("RapRobot")
    pygame.mouse.set_visible(False)
    screen = pygame.display.set_mode(SCREEN_RESOLUTION)
    screen.fill((0,0,0))
    pygame.display.update()
    font = pygame.font.Font("assets/HN.otf", FONT_SIZE)

def checkMessages():
    global myTwitterStream, mySmsStream
    global lastTwitterCheck, lastSmsCheck
    ## check twitter queue
    if((time()-lastTwitterCheck > 5) and (not myTwitterStream.empty())):
        print("Checking twitter %s", time())
        tweet = myTwitterStream.get().lower()
        tweet = unidecode(tweet)
        ## removes re-tweet
        tweet = re.sub(r'(^[rR][tT] )', '', tweet)
        ## removes hashtags, arrobas and links
        tweet = re.sub(r'(#\S+)|(@\S+)|(http://\S+)', '', tweet)
        ## remove NeuralNetProcessor
        tweet = re.sub(r"http\S+", "", tweet)
        ## clean, tag and send text
        now = datetime.now(utc)
        logFile.write(now.isoformat() + "  ***  "+ unidecode(tweet) +"\n")
        logFile.flush()
        lastTwitterCheck = time()

        return tweet


    ## check sms
    if((time()-lastSmsCheck > 2) and (not mySmsStream.empty())):
        print("Checking sms %s", time())
        sms = mySmsStream.get().lower()
        now = datetime.now(utc)
        logFile.write(now.isoformat() + "  ***  "+ unidecode(sms) +"\n")
        logFile.flush()
        lastSmsCheck = time()

        return sms

    return unicode('', 'utf8')

def printText(msg):
    global printer
    try:
        printer.setSize('L')   # Set type size, accepts 'S', 'M', 'L'
        printer.println('#RapRobot')
        printer.feed(1)
        printer.setSize('S')
        printer.justify('L')
        printer.println(unidecode(msg))
        printer.feed(4)
    except NameError:
        print('No printer is present')

class Flow(Enum):
    CHECK_MSGS = 1
    PROCESS_MSG = 2
    WAIT_OUTPUT = 3
    PRINT = 4
    DISPLAY_PRINT = 5
    NOTHING = 6

if __name__=="__main__":
    setup()

    try:
        state = Flow.CHECK_MSGS
        msg = unicode('', 'utf8')
        lastTime = None
        enablePrinter = False
        while(True):

            if state == Flow.CHECK_MSGS:
                msg = checkMessages()
                if msg is not '':
                    state = Flow.PROCESS_MSG
            elif state == Flow.PROCESS_MSG:
                myNeuralNet.start(msg)
                state = Flow.WAIT_OUTPUT
            elif state == Flow.WAIT_OUTPUT:
                if(not myNeuralNet.isProcessing):
                    state = Flow.PRINT
                    msg = myNeuralNet.lastOutput
            elif state == Flow.PRINT:
                    if enablePrinter:
                        printerThread = Thread(target=printText, args=(msg,))
                        printerThread.setName('PrinterThread')
                        printerThread.start()
                    state = Flow.DISPLAY_PRINT
                    lastTime = time()
            elif state == Flow.DISPLAY_PRINT:
                if(time() - lastTime > 10):
                    state = Flow.CHECK_MSGS
            elif state == Flow.NOTHING:
                state = Flow.NOTHING

            screen.fill((0,0,0))

            my_rect = pygame.Rect((10, 10, 480-20, 800-20))
            my_text = render_textrect(unidecode(msg), font, my_rect, (216, 216, 216), (48, 48, 48), 0)
            my_text = pygame.transform.rotate(my_text, 90)
            screen.blit(my_text, my_rect.topleft)
            pygame.display.update()

            for event in pygame.event.get():
                if event.type  == pygame.KEYDOWN and event.key == pygame.K_a:
                    pygame.display.toggle_fullscreen()
                elif event.type  == pygame.KEYDOWN and event.key == pygame.K_p:
                    enablePrinter = not enablePrinter
                    print('EnablePrinter', enablePrinter)
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    raise SystemExit
                elif event.type ==  pygame.QUIT:
                    raise SystemExit


    except KeyboardInterrupt, SystemExit:
        pygame.quit()
        logFile.close()
        myTwitterStream.disconnect()
        sys.exit(0)
