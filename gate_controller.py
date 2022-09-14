import logging
import os
import time
import sys

from threading import Timer

import RPi.GPIO as GPIO

LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig(stream=sys.stdout, level=LOGLEVEL)
# logger.debug("Debug test")
# logger.info("Info test")

LED_PIN=8

# Configure the board
GPIO.setmode(GPIO.BOARD) # Use Board numbers https://pinout.xyz/
#GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.setwarnings(False)

class GateController():
    def _init_(self):
        self.connected = False

    def open(self, hold=1):
        logger.info("Triggering open")
        self._connect_exit()
        Timer(hold, self._disconnect_exit).start()

    def is_connected(self):
        return self.connected

    def _connect_exit(self):
        logger.info("Connecting")
        self.connected = True
        GPIO.output(LED_PIN, True)

    def _disconnect_exit(self):
        logger.info("Disonnecting")
        self.connected = False
        GPIO.output(LED_PIN, False)

if __name__ == '__main__':
    while True:
        logger.info("Opening for 5 seconds, sleeping for 10")
        GateController().open(5)
        time.sleep(10)     