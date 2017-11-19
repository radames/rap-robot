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
from subprocess32 import TimeoutExpired, check_output, STDOUT
import pygame
from pygame.locals import *

utc=pytz.UTC

SCREEN_RESOLUTION = (800, 480)

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

def setup():
    global myTwitterStream, mySmsStream
    global lastTwitterCheck, lastSmsCheck
    global PHONE_NUMBER
    global logFile
    global screen, font
    lastTwitterCheck = time()
    lastSmsCheck = time()

    try:
        printer = Adafruit_Thermal("/dev/tty.usbserial", 9600, timeout=5)
        printer.begin(255)
    except:
        print('Error loading serial port...')


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
    mySmsStream =  SMSReceiver(data["twilio"]['ACCOUNT_SID'], data["twilio"]['AUTH_TOKEN'])
    smsStreamThread = Thread(target=mySmsStream.update)
    smsStreamThread.daemon = True
    smsStreamThread.start()
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
    font = pygame.font.Font("assets/HN.otf", 50)

def cleanTagAndSendText(text):
    ## removes punctuation
    # text = re.sub(r'[.,;:!?*/+=\-&%^/\\_$~()<>{}\[\]]', ' ', text)
    ## replaces double-spaces with single space
    # text = re.sub(r'( +)', ' ', text)

    ## log
    now = datetime.now(utc)
    logFile.write(now.isoformat() + "  ***  "+ unidecode(text) +"\n")
    logFile.flush()

def getNeuralNetText(start_text):
    cmd = ['python', 'sample.py', '--init_dir', 'pretrained_shakespeare', '--start_text', start_text]
    cwd ='./tensorflow-char-rnn'
    try:
        outs = check_output(cmd, cwd=cwd, stderr=STDOUT, timeout=60)
        return outs
    except TimeoutExpired:
        logFile.write("Command timed out --- tensorflow problem")
        print('ERROR processing tensorflow')
        return 0

def loop():
    global myTwitterStream, mySmsStream
    global lastTwitterCheck, lastSmsCheck
    ## check twitter queue
    if((time()-lastTwitterCheck > 5) and (not myTwitterStream.empty())):
        print("Checking twitter %s", time())
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
    if((time()-lastSmsCheck > 2) and (not mySmsStream.empty())):
        print("Checking sms %s", time())
        sms = mySmsStream.get().lower()
        cleanTagAndSendText(sms)
        lastSmsCheck = time()

def toggle_fullscreen():
    #from http://pygame.org/wiki/toggle_fullscreen
    screen = pygame.display.get_surface()
    tmp = screen.convert()
    caption = pygame.display.get_caption()
    #cursor = pygame.mouse.get_cursor()  # Duoas 16-04-2007

    w,h = screen.get_width(),screen.get_height()
    flags = screen.get_flags()
    bits = screen.get_bitsize()

    pygame.display.quit()
    pygame.display.init()

    screen = pygame.display.set_mode((w,h),flags^FULLSCREEN,bits)
    screen.blit(tmp,(0,0))
    pygame.display.set_caption(*caption)

    pygame.key.set_mods(0) #HACK: work-a-round for a SDL bug??

    #pygame.mouse.set_cursor( *cursor )  # Duoas 16-04-2007

    return screen

if __name__=="__main__":
    setup()

    try:
        while(True):
            loop()
            screen.fill((0,0,0))
            t = time()
            text = font.render(str(t), True, (255,255,255))
            text = pygame.transform.rotate(text, 90)
            rect = text.get_rect(center=(200,240))
            screen.blit(text, rect)
            pygame.display.update()

            for event in pygame.event.get():
                if event.type  == pygame.KEYDOWN and event.key == pygame.K_a:
                    screen = toggle_fullscreen()
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    raise SystemExit
                elif event.type ==  pygame.QUIT:
                    raise SystemExit


    except KeyboardInterrupt, SystemExit:
        pygame.quit()
        logFile.close()
        myTwitterStream.disconnect()
        sys.exit(0)
