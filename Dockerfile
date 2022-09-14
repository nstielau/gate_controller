FROM balenalib/raspberrypi3-python:3.9-bullseye-build

ENV VERSION=1.0.0
RUN python --version

# Intall the rpi.gpio python module
RUN pip install --upgrade pip
RUN echo [global] > /etc/pip.conf && echo extra-index-url=https://www.piwheels.org/simple >> /etc/pip.conf
RUN pip install --no-cache-dir rpi.gpio
RUN pip install --no-cache-dir bottle
RUN pip install --no-cache-dir cryptography --prefer-binary
RUN pip install --no-cache-dir ask-sdk
RUN pip install --no-cache-dir ask-sdk-webservice-support


# Copy the Python files
COPY gate_controller.py ./
COPY server.py ./

# Trigger Python script
CMD ["python", "server.py"]
