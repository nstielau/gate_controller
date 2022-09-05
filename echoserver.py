import json
import logging
import os
import sys

from screenlogic.screenlogic import slBridge    

from bottle import route, run, template, request

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

#####################################################################
#####################################################################
# Handlers
#####################################################################

skill_builder = SkillBuilder()

@skill_builder.request_handler(can_handle_func=is_request_type("LaunchRequest"))
def launch_request_handler(handler_input):
    speech_text = "Pool party time"

    handler_input.response_builder.speak(speech_text).set_card(
        SimpleCard(speech_text, speech_text)).set_should_end_session(False)
    return handler_input.response_builder.response

@skill_builder.request_handler(can_handle_func=is_intent_name("StartSwimJetIntent"))
def start_swimjet_intent_handler(handler_input):
    speech_text = "Pool jet started"

    slBridge(True).setCircuit(502, 1)

    handler_input.response_builder.speak(speech_text).set_card(
        SimpleCard(speech_text, speech_text)).set_should_end_session(True)
    return handler_input.response_builder.response

@skill_builder.request_handler(can_handle_func=is_intent_name("StopSwimJetIntent"))
def stop_swimjet_intent_handler(handler_input):
    speech_text = "Pool jet stopped"

    slBridge(True).setCircuit(502, 0)

    handler_input.response_builder.speak(speech_text).set_card(
        SimpleCard(speech_text, speech_text)).set_should_end_session(True)
    return handler_input.response_builder.response

@skill_builder.request_handler(
    can_handle_func=lambda handler_input :
        is_intent_name("AMAZON.CancelIntent")(handler_input) or
        is_intent_name("AMAZON.StopIntent")(handler_input))
def cancel_and_stop_intent_handler(handler_input):
    # type: (HandlerInput) -> Response
    speech_text = "Party on!"

    handler_input.response_builder.speak(speech_text).set_card(
        SimpleCard("Party on", speech_text)).set_should_end_session(
            True)
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
def index():
    return "hello"

@route('/', method=['POST'])
def index():
    body = request.body.read().decode()
    headers = request.headers
    logger.info(headers)
    pretty_print_json(body)
    return webservice_handler.verify_request_and_dispatch(headers, body)

run(host='0.0.0.0', port=80)
