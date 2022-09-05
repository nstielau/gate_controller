import logging
import os
import time
import sys

import RPi.GPIO as GPIO

LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig(stream=sys.stdout, level=LOGLEVEL)
logger.debug("Debug test")
logger.info("Info test")

BUTTON_PIN=40
LED_PIN=8

# Configure the board
GPIO.setmode(GPIO.BOARD) # Use Board numbers https://pinout.xyz/
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.setwarnings(False)

def button_callback(channel):
    logger.info("Button was pushed!")
    GPIO.output(LED_PIN, True)
    time.sleep(0.2)    
    GPIO.output(LED_PIN, False)

GPIO.add_event_detect(BUTTON_PIN, GPIO.RISING, callback=button_callback) # Setup event on pin rising edge

while True:
    GPIO.output(LED_PIN, True)
    time.sleep(0.2)    
    GPIO.output(LED_PIN, False)