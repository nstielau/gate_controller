FROM balenalib/raspberrypi3-python:3.10-bullseye-build

ENV VERSION=1.0.0
RUN python --version

# Intall the rpi.gpio python module
RUN pip install --upgrade pip
RUN pip install --no-cache-dir rpi.gpio

# Copy the Python files
COPY gate_controller.py ./

# Trigger Python script
CMD ["python", "gate_controller.py"]
