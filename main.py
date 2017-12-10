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
from twython import Twython, TwythonError
from twilio.rest import Client
import pytz
from unidecode import unidecode
from subprocess32 import check_output, STDOUT, CalledProcessError
import pygame
from pygame.locals import *
from enum import Enum
from utils import *

utc=pytz.UTC

SCREEN_RESOLUTION = (800, 480)
FONT_SIZE = 20
TWITTER_HANDLE = "rapresearchlab"
TWITTER_HASH =  " #rapbot"
class TwitterStreamReceiver(TwythonStreamer):
    def __init__(self, *args, **kwargs):
        super(TwitterStreamReceiver, self).__init__(*args, **kwargs)
        self.tweetQ = Queue()
    def on_success(self, data):
        if ('text' in data and data['user']['screen_name'] != TWITTER_HANDLE):
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
        def __init__(self, working_path, model_path, length, temp):
            self.cmd = ['python', 'sample.py', '--init_dir', model_path, '--length', length, '--temperature', temp, '--start_text']
            self.cwd = working_path
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
            try:
                out = check_output(self.cmd + [self.start_text], cwd=self.cwd, stderr=STDOUT, shell=False, timeout=60)
            except CalledProcessError as e:
                print(e.output)
                logFile.write('ERROR ON SUBPROCESS\n');
                self.isProcessing = False
                return

            self.lastOutput = out
            self.isProcessing = False
            logFile.write('Processed MSG --->  ' + out + '\n');

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
    global myTwitterStream, myTwitterClient, mySmsStream
    global lastTwitterCheck, lastSmsCheck
    global myNeuralNet
    global PHONE_NUMBER,PHONE_FORMAT
    global logFile
    global screen, font, font_title
    global printer
    lastTwitterCheck = time()
    lastSmsCheck = time()

    with open('secrets.json') as dataFile:
        data = json.load(dataFile)
        ## What to search for
    SEARCH_TERMS = data["search_terms"]
    PHONE_NUMBER = data["phone_number"]
    PHONE_FORMAT='({}) {}-{}'.format(PHONE_NUMBER[2:5], PHONE_NUMBER[5:8], PHONE_NUMBER[8:])
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
    #twitter client to post twitts
    myTwitterClient = Twython(app_key = data["twitter"]['CONSUMER_KEY'],
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

    myNeuralNet = NeuralNetProcessor(data['working_path'], data['model_path'], data['length'], data['temperature'])

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
    font_title = pygame.font.Font("assets/HN.otf", FONT_SIZE*2)

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
        tweet = tweet.strip()
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

    return None

def printText(msg):
    global printer
    try:
        printer.setSize('L')   # Set type size, accepts 'S', 'M', 'L'
        printer.println('#Rapbot')
        printer.feed(1)
        printer.setSize('S')
        printer.justify('L')
        printer.println(unidecode(msg))
        printer.feed(4)
    except NameError:
        print('No printer is present')

def tweetMsg(msg):
    global myTwitterClient

    def getTweet(msg):
        tweet = ""
        for e in msg.split():
             tweet += " " + e
             if(len(tweet) >=200):
                 yield tweet
                 tweet = ""
        yield tweet

    try:
        head = ""
        firstTweetID = None
        for tweet in getTweet(msg):
            print(tweet)
            print("\n")
            t = myTwitterClient.update_status(status= head + tweet + TWITTER_HASH, in_reply_to_status_id = firstTweetID)
            if(firstTweetID == None):
                firstTweetID = t['id']
                head = "@"+ TWITTER_HANDLE + " "
            sleep(1)

    except TwythonError as e:
        print(e)

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
        msg = None
        lastTime = 0
        enablePrinter = True
        enableTweet = True
        while(True):

            if state == Flow.CHECK_MSGS:
                msg = checkMessages()
                if msg is not None:
                    state = Flow.PROCESS_MSG
            elif state == Flow.PROCESS_MSG:
                myNeuralNet.start(msg)
                state = Flow.WAIT_OUTPUT
                lastTime = time()
                msg += " "
            elif state == Flow.WAIT_OUTPUT:
                if(time() - lastTime > 1):
                    msg += "."
                    lastTime = time()
                if(not myNeuralNet.isProcessing):
                    state = Flow.PRINT
                    msg = myNeuralNet.lastOutput.lstrip('Sampled text is:')
            elif state == Flow.PRINT:
                    if enableTweet:
                        tweetMsgThread = Thread(target=tweetMsg, args=(msg,))
                        tweetMsgThread.setName("tweetMsgThread")
                        tweetMsgThread.start()
                    if enablePrinter:
                        printerThread = Thread(target=printText, args=(msg,))
                        printerThread.setName('PrinterThread')
                        printerThread.start()
                    state = Flow.DISPLAY_PRINT
                    lastTime = time()
            elif state == Flow.DISPLAY_PRINT:
                if(time() - lastTime > 30):
                    state = Flow.CHECK_MSGS
            elif state == Flow.NOTHING:
                state = Flow.NOTHING


            if(msg is None):
                t = "\n#Rapbot\n\nText to:\n\n"+PHONE_FORMAT
                my_rect = pygame.Rect((200, 40, 400, 300))
                my_text = render_textrect(unidecode(t), font_title, my_rect, (216, 216, 216), (48, 48, 48), 1)
                my_text = pygame.transform.rotate(my_text, -90)
                lastFlick = time()
                screen.blit(my_text, my_rect.topleft)
            else:
                spaces = "\n\n"
                my_rect = pygame.Rect((10, 10, 480-20, 800-20))
                my_text = render_textrect(unidecode(spaces+msg), font, my_rect, (216, 216, 216), (48, 48, 48), 0)
                my_text = pygame.transform.rotate(my_text, -90)
                screen.blit(my_text, my_rect.topleft)


            for event in pygame.event.get():
                if event.type  == pygame.KEYDOWN and event.key == pygame.K_a:
                    pygame.display.toggle_fullscreen()
                elif event.type  == pygame.KEYDOWN and event.key == pygame.K_p:
                    enablePrinter = not enablePrinter
                    print('EnablePrinter', enablePrinter)
                    my_text = render_textrect('EnablePrinter: ' + str(enablePrinter), font_title, my_rect, (216, 216, 216), (48, 48, 48), 1)
                    my_text = pygame.transform.rotate(my_text, -90)
                    screen.blit(my_text, my_rect.topleft)
                elif event.type  == pygame.KEYDOWN and event.key == pygame.K_t:
                    enableTweet = not enableTweet
                    print('Disable Twitter', enableTweet)
                    my_text = render_textrect('Enable Twitter: ' + str(enableTweet), font_title, my_rect, (216, 216, 216), (48, 48, 48), 1)
                    my_text = pygame.transform.rotate(my_text, -90)
                    screen.blit(my_text, my_rect.topleft)
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    raise SystemExit
                elif event.type ==  pygame.QUIT:
                    raise SystemExit

            pygame.display.update()


    except KeyboardInterrupt, SystemExit:
        pygame.quit()
        logFile.close()
        myTwitterStream.disconnect()
        sys.exit(0)
