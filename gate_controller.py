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

GATE_PIN=8

# Configure the board
GPIO.setmode(GPIO.BOARD) # Use Board numbers https://pinout.xyz/
GPIO.setup(GATE_PIN, GPIO.OUT)
GPIO.setwarnings(False)

class GateController():
    def __init__(self):
        self._connected = False
        self._timer = None

    def request_open(self, duration=1):
        logger.info("Triggering hold")
        self._connect_exit()
        self._timer = Timer(duration, self._disconnect_exit)
        self._timer.start()

    def is_held(self):
        return self._connected

    def cancel_hold(self):
        logger.info("Releasing hold")
        self._timer.cancel()
        self._disconnect_exit()

    def _connect_exit(self):
        logger.info("Connecting")
        self._connected = True
        GPIO.output(GATE_PIN, True)

    def _disconnect_exit(self):
        logger.info("Disonnecting")
        self._connected = False
        GPIO.output(GATE_PIN, False)

if __name__ == '__main__':
    while True:
        logger.info("Opening for 5 seconds, sleeping for 10")
        GateController().request_open(5)
        time.sleep(10)