# It's assumed that users are building the image from the directory where this file lives
# using this command:
#    docker build . -t soilmap-rpp-server:latest
# Optionally, it is assumed that users *may* have symlinked the built version of the Nodemaker UI

FROM public.ecr.aws/lambda/python:3.8
# FROM ubuntu:latest

ARG PODPAC_VERSION="3.2.0"
ARG DEBIAN_FRONTEND=noninteractive
ARG SOILMAP_KEY
ARG WG_KEY
# ARG ROOT_DIR=/app/
ARG ROOT_DIR=${LAMBDA_TASK_ROOT}
ENV TZ=America/New_York
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# development tools
# RUN apt-get update && apt-get install -y build-essential git
RUN yum install -y gcc-c++ git

# Python dependencies install
# RUN apt-get update && apt-get -y install python3 python3-pip

# Update pip
RUN python3 -m pip install --upgrade pip

# Python tools
RUN pip3 install ipython black pre-commit attrs --use-deprecated=legacy-resolver

# RPP-Server dependencies
RUN pip3 install matplotlib flask markdown webob botocore boto3 lxml flask-cors Cython ipyleaflet numpy s3fs --use-deprecated=legacy-resolver

# # Install podpac
# RUN pip3 install podpac[datatype,aws,algorithms,stac]==$PODPAC_VERSION
RUN pip install "podpac[all]==3.2.0" --use-deprecated=legacy-resolver


# Make working directories
# RUN mkdir ${ROOT_DIR} && mkdir ${ROOT_DIR}/data
RUN echo "Installing SoilMAP"
RUN mkdir ${ROOT_DIR}/data && chmod a+rwx ${ROOT_DIR}/data

# Copy as late as possible to avoid cache-busting
WORKDIR ${ROOT_DIR}
RUN git clone https://github.com/creare-com/ogc.git

# Install soilmap RPP server and other dependencies
RUN cd ${ROOT_DIR}/ogc && \
    git fetch && \
    git checkout main &&\
    pip3 install -e . --use-deprecated=legacy-resolver && \
    rm -r .git

## Install gunicorn to run a non-aws-lambda server
RUN pip3 install gunicorn

# For AWS Lambda using API Gateway (old)
# RUN pip3 install aws-wsgi

# 2022 we can now avoid API gateway, but need version 2.0 of the aws-wsgi package
# which is not on pypy -- in fact we have to go a fork for the fix
RUN pip install git+https://github.com/c3ko/awsgi.git@api-gateway-v2-format --use-deprecated=legacy-resolver

# Fix broken packages
RUN pip3 install markupsafe==2.0.1 --use-deprecated=legacy-resolver
RUN pip install pysolar pydap==3.2.1 --use-deprecated=legacy-resolver
RUN pip install traitlets==5.6 --use-deprecated=legacy-resolver

# Cleaning up a bit
RUN pip3 cache purge

WORKDIR ${ROOT_DIR}

# For testing or running a gunicorn server
# EXPOSE 5000
# CMD ["gunicorn", "-b", "0.0.0.0:5000", "-t", "0", "-w", "8", "server:app"]

# For deployment on AWS
# For the lambda function
EXPOSE 8080
CMD [ "server.lambda_handler" ]

# Delay copy as late as possible to avoid cache busting
COPY src/*.py ${ROOT_DIR}/
COPY data/settings.json ${ROOT_DIR}/settings.json
COPY data/layers.json ${ROOT_DIR}/data/layers.json

# This step is optional and should be used when the NodeMaker UI is included
COPY src/node-maker ${ROOT_DIR}/node-maker
