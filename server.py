import json
import logging
import os
import sys

from gate_controller import GateController

from bottle import route, run, template, request, response

from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_webservice_support.webservice_handler import WebserviceSkillHandler
from ask_sdk_core.utils import is_request_type, is_intent_name
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_model import Response
from ask_sdk_model.ui import SimpleCard

LOGLEVEL = os.environ.get('LOGLEVEL', 'INFO').upper()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig(stream=sys.stdout, level=LOGLEVEL)
logger.debug("Debug test")
logger.info("Info test")


gate_controller = GateController()

#####################################################################
#####################################################################
# Handlers
#####################################################################

skill_builder = SkillBuilder()

@skill_builder.request_handler(can_handle_func=is_request_type("LaunchRequest"))
def launch_request_handler(handler_input):
    speech_text = "Opening the gate"

    gate_controller.open()

    handler_input.response_builder.speak(speech_text).set_card(
        SimpleCard(speech_text, speech_text)).set_should_end_session(True)
    return handler_input.response_builder.response

@skill_builder.request_handler(
    can_handle_func=lambda handler_input :
        is_intent_name("AMAZON.CancelIntent")(handler_input) or
        is_intent_name("AMAZON.StopIntent")(handler_input))
def cancel_and_stop_intent_handler(handler_input):
    # type: (HandlerInput) -> Response
    speech_text = "Cancelling!"

    handler_input.response_builder.speak(speech_text).set_card(
        SimpleCard(speech_text, speech_text)).set_should_end_session(True)
    return handler_input.response_builder.response

@skill_builder.exception_handler(can_handle_func=lambda i, e: True)
def all_exception_handler(handler_input, exception):
    print(exception)

    speech = "Sorry, I didn't get it. Can you please say it again!!"
    handler_input.response_builder.speak(speech).ask(speech)
    return handler_input.response_builder.response

webservice_handler = WebserviceSkillHandler(skill=skill_builder.create())



#####################################################################
#####################################################################
# helpers
#####################################################################
def pretty_print_json(json_data):
    logger.debug(json.dumps(json.loads(json_data), indent=2))

#####################################################################
#####################################################################
# Webserver
#####################################################################
@route('/', method=['GET'])
def get_index():
    return {"messsage": "I'm a gate!"}

@route('/hold', method=['DELETE'])
def delete_hold():
    response.set_header('Access-Control-Allow-Origin', '*')
    response.add_header('Access-Control-Allow-Methods', 'GET, POST, DELETE')
    gate_controller.cancel_hold()
    return {
        "message": "Cancelled hold",
        "connected": gate_controller.is_held()
    }

@route('/hold', method=['GET'])
def get_hold():
    response.set_header('Access-Control-Allow-Origin', '*')
    response.add_header('Access-Control-Allow-Methods', 'GET, POST, DELETE')
    return {"connected": gate_controller.is_held()}

@route('/hold', method=['POST'])
def post_hold():
    response.set_header('Access-Control-Allow-Origin', '*')
    response.add_header('Access-Control-Allow-Methods', 'GET, POST, DELETE')
    try:
        hold_secs = request.body.read().decode()
        gate_controller.request_open(int(hold_secs))
        return {
            "message": "Gate held open for " + str(hold_secs) + " seconds"
        }
    except:
        gate_controller.request_open()
        return {
            "message": "Opened Gate"
        }

@route('/open', method=['GET'])
def get_open():
    # DEPRECATED IN FAVOR OF /hold
    response.set_header('Access-Control-Allow-Origin', '*')
    response.add_header('Access-Control-Allow-Methods', 'GET, POST')
    return {
        "connected": gate_controller.is_held(),
        "message": "Deprecated in favor of /hold"
    }

@route('/open', method=['POST'])
def post_open():
    # DEPRECATED IN FAVOR OF /hold
    response.set_header('Access-Control-Allow-Origin', '*')
    response.add_header('Access-Control-Allow-Methods', 'GET, POST')
    try:
        hold_secs = request.body.read().decode()
        gate_controller.request_open(int(hold_secs))
        return {
            "message": "Gate held open for " + str(hold_secs) + " seconds"
        }
    except:
        gate_controller.request_open()
        return {
            "message": "Opened Gate. Deprecated in favor of /hold"
        }

@route('/', method=['POST'])
def post_index():
    body = request.body.read().decode()
    headers = request.headers
    logger.info(headers)
    pretty_print_json(body)
    return webservice_handler.verify_request_and_dispatch(headers, body)

run(host='0.0.0.0', port=80)
