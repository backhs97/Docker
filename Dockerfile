FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt 
# Install Python dependencies
RUN apt-get update -y
RUN apt-get install net-tools
RUN apt-get install -y iputils-ping
# Install network tools for debugging

COPY node.py .
# Copy the Python script into the container

CMD python node.py
# Set the default command to run the Python script


# python node.py
# tail -f  /dev/null 
#^ command to keep the instance running forever
