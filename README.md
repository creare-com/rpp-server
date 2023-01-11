# SoilMAP RPP Server #

The SoilMAP RPP server is a generic Geospatial data server. Users can programmatically (through http get/post requests) or graphically (using the NodeMaker UI) add
Geospatial products (data files and processing pipelines) to this server. The added products are then exposed via automatically generated WCS/WMS endpoints.

## Dependencies
Uses Python 3.8

There is a [requirements.txt](requirements.txt) file that lists the output of `pip freeze`. There is also a [requirements_minimal.txt](requirements_minimal.txt) file that give
the minimal requirements.

## Quick Start

### Running a local server

Starting from a fresh python virtual environment
```
git clone git+git@github.com:creare-com/rpp-server.git
cd rpp-server
pip install -r requirements.txt --use-deprecated=legacy-resolver
cd src
python server.py
```

### Running a local server through Docker
Starting from an empty folder:
```
git clone git+git@github.com:creare-com/rpp-server.git
cd rpp-server
docker build . -t soilmap-rpp-server-oss:latest
docker run \
    --rm -itp 5000:5000 --entrypoint python \
    -v $(pwd)/data/settings.json:/var/task/settings.json  \
    -v $(pwd)/data:/var/task/data  \
    soilmap-rpp-server-oss:latest server.py
```
Then navigate to [https://localhost:5000](https://localhost:5000). An example query would be: `http://localhost:5000/api/publish/?KEY=onlySomeUsersKnowThis&SERVICE=query&verbose=True`

The image created by default can be deployed to an AWS Lambda function. If you'd rather have it run through Gunicorn, change the Docker file
as follows:
```
# For testing or running a gunicorn server
EXPOSE 5000
CMD ["gunicorn", "-b", "0.0.0.0:5000", "-t", "0", "-w", "8", "server:app"]


# For deployment on AWS
# For the lambda function
# EXPOSE 8080
# CMD [ "server.lambda_handler" ]
```

## Adding the NodeMaker UI
To add the NodeMaker UI, follow the build instructions for the [node-maker](https://github.com/creare-com/node-maker)

Once the NodeMaker app is built, copy the static files to `<root-path>/rpp-server/src/node-maker`

```bash
cp -r <root-path>/node-maker/dist/node-maker <root-path>/rpp-server/src/node-maker
```
where `<root-path>` is the folder where the `rpp-server` and `node-maker` repositories are checked out.

If you want to use the `node-maker` in your Docker image, uncomment the last line of the image
`COPY src/node-maker ${ROOT_DIR}/node-maker` before running the build command

## Modifying settings
The `data/setting.json` is a PODPAC settings file and can be used to modify any PODPAC defaults. The `rpp-server` uses
this settings file to specify the secret keys privileged users need to use to publish new data products. The default
key is `onlySomeUsersKnowThis` and should be replaced by users. The NodeMaker hard-codes this secret to allow anyone
to add new products, which might be fine depending on your use case.
