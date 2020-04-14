FROM tidair/smurf-rogue:R2.7.0

# Install pyipmi
RUN pip3 install python-ipmi

# Add this code
WORKDIR /usr/local/src
RUN mkdir smurf-atca-monitor
ADD . smurf-atca-monitor
WORKDIR smurf-atca-monitor
ENV PYTHONPATH /usr/local/src/smurf-atca-monitor/python:${PYTHONPATH}

# Start the attca_monitor application by default
# The needed arguments can be passed to the docker run command
ENTRYPOINT ["./atca_monitor.py"]
