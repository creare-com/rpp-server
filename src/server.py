import json
import os
from datetime import datetime

import matplotlib
from flask import request, make_response, send_from_directory
import requests

from podpac import settings
import podpac.datalib
from flask_cors import CORS

from authentication import authorize, wrap_html_and_forward_auth_token
from utils import _uppercase_for_dict_keys, _string_to_html, parse_url
from publishing_api import publish_pipeline, query_pipeline, remove_pipeline
from server_layers import Layers, home

"""
Below are the remaining imports that should be 'cleaned' for open-source release.
"""
import ogc, ogc.core, ogc.servers

matplotlib.use("agg")


#############
# SETTINGS  #
#############
APP_ROOT = "/api/"  # Require trailing slash
def DEFAULT_COORDS():
    return podpac.Coordinates([
        podpac.clinspace(90, -90, 648000, 'lat'),
        podpac.clinspace(-180, 180, 1296000, 'lon'),
        podpac.crange("2010-01-01", datetime.now().strftime('%Y-%m-%d'), "1,D", 'time'),
    ])

# Update settings from environmental variables on the image (this take precedence over the JSON file)
settings.update(json.loads(os.environ.get("SETTINGS", "{}")))
settings.allow_unrestricted_code_execution(True)

# Updating environmental variables so that Rasterio will properly access S3 files on govcloud
AWS_SETTINGS = ["AWS_S3_ENDPOINT", "AWS_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID", "AWS_DEFAULT_REGION"]
for setting in AWS_SETTINGS:
    if settings[setting]:
        os.environ[setting] = settings[setting]
print (os.environ)

#######################################
# SETTING UP LAYERS AND OGC ENDPOINTS #
#######################################

LAYERS = Layers(source=settings["PUBLISHED_PIPELINES"]["path"])
print("="*80)
print('STARTING LAYERS')
print(LAYERS.ogc_layers)
print("="*80)

#########################
#     AUTHENTICATION    #
#########################
if "ACCESS_TOKENS" not in settings:
    print("WARNING: ACCESS_TOKENS have not been configured for this server. Users will NOT be able to log in.")
    print("""To set up authentication token for a new user use:
    >>> import uuid, hashlib
    >>> new_token = str(uuid.uuid4())
    >>> print("Share this token with the user", new_token)
    >>> access_token = hashlib.sha256(new_token.encode('utf-8')).hexdigest()
    >>> print("Manually add access_token to `settings.json` file, or evaluate code below:", access_token)
    >>> from podpac import settings
    >>> access_tokens = settings.get("ACCESS_TOKENS", [])
    >>> access_tokens.append(access_token)
    >>> settings["ACCESS_TOKENS"] = access_tokens
    >>> settings.save()
    """)

############################
#    SETTING UP THE APP    #
############################

OGC = ogc.core.OGC(
    endpoint=APP_ROOT,
    layers=list(LAYERS.ogc_layers),
    service_group_title="SoilMAP RPP Layers"
)
class FlaskServerDynamic(ogc.servers.FlaskServer):
    @authorize
    def ogc_render(self, ogc_idx):
        # Optimization, if this is an WMS  or WCS request, just make sure the requested layer is updated
        #  convert to lower-case.
        args = {k.lower(): str(v) for (k, v) in request.args.items()}
        if False: #(args.get('service', '').lower() == 'wcs' and args.get('request', '').lower() == "getcoverage") or \
            # (args.get('service', '').lower() == 'wms' and args.get('request', '').lower() == 'getmap'):
            identifier = args.get('layers', args.get('coverage'))
            print("Just updating one layer for WMS/WCS", args)
            sf = LAYERS.skip_failed
            LAYERS.skip_failed = True
            self.ogcs[ogc_idx] = ogc.core.OGC(
                endpoint=APP_ROOT,
                layers=list(LAYERS.ogc_layers),
                service_group_title="SoilMAP RPP Layers"
            )
            LAYERS.skip_failed = sf

        else:
            print("Updating ALL layers", args)
            # Need to overwrite ogc_render to dynamically add layers -- since these can change
            LAYERS.skip_failed = False
            self.ogcs[ogc_idx] = ogc.core.OGC(
                endpoint=APP_ROOT,
                layers=list(LAYERS.ogc_layers),
                service_group_title="SoilMAP RPP Layers"
            )

        # also need to overwrite ogc_render to allow the TOKEN arg
        if len(request.args) == 1 and list(request.args.keys())[0].upper() == "TOKEN":
            return self.home_func(self.ogcs[ogc_idx])
        return super().ogc_render(ogc_idx)

    def add_url_rule(self,
            rule,
            endpoint=None,
            view_func=None,
            provide_automatic_options=None,
            **options):
        # Need to overwrite base flask.add_url_rule method to add our authentication approach
        # add authentication to view_func
        if 'rule' == APP_ROOT:
            view_func = authorize(view_func)
        # print("endpoint", endpoint, "rule", rule)
        super().add_url_rule(rule, endpoint, view_func, provide_automatic_options, **options)

app = FlaskServerDynamic(
    __name__,
    ogcs=[OGC, ],
    home_func=lambda ogc: wrap_html_and_forward_auth_token(home(ogc)))#, static_url_path='ui')
CORS(app)

##########################
# AWS Lambda Integration #
##########################
def lambda_handler(event, context):
    import awsgi
    print("EVENT", event, "\nCONTEXT", context)
    return awsgi.response(app, event, context, base64_content_types={"image/png", "image/gif"})


####################
# SERVER ENDPOINTS #
####################

@app.route('/')
@authorize
def root():
    return wrap_html_and_forward_auth_token("""<h1> SoilMAP RPP Server </h1>
    <p>This server provides OGC-compliant WCS/WMS endpoints to serve geospatial products created using SoilMAP.</p>
    <p>For users with an approved server key, new data products can be published using the <a href="api/publish/">api/publish/</a> endpoint.</p>
    <p>To create pipelines interactively, you can use <a href="ui/NodeMaker"> NodeMaker user interface</a>. </p>
    <p>For help, visit the API documentation at <a href="api/">api/</a>. </p>
    <p>API users can plan routes using the <a href="api/route/">api/route/</a> endpoint.</p>
    <p>This server is built using the open source <a href="https://podpac.org">PODPAC library</a>. </p>
    """)

@app.route(APP_ROOT+"publish/UI_spec")
@authorize
def publish_UI_route():
    """
    This route sends podpac specifications including node information, interpolation methods and colormaps to the node-maker app.
    """
    categories = podpac.core.utils.get_ui_node_spec(help_as_html=True)
    cat_reverse = {categories[cat][node]["module"]: cat for cat in categories for node in categories[cat]}
    podpac_version = podpac.version.semver()
    ui_spec = {
        "categories": categories,
        "categories_reverse": cat_reverse,
        "interpolators": podpac.data.INTERPOLATION_METHODS,
        "color_maps": matplotlib.pyplot.colormaps(),
        "version_info": {
            "podpac": podpac_version
        }
    }
    json_spec = json.dumps(ui_spec, cls=podpac.core.utils.JSONEncoder)
    # np.nan gets converted to NaN, which is not json decodable, so we have to replace that
    json_spec = json_spec.replace('NaN', 'null')
    response = make_response(json_spec)
    response.headers.set("Content-Type", "application/json")
    response.content_type = "application/json"
    response.mimetype = "application/json"
    return response

@app.route('/ui', methods=["GET"])
def send_node_maker_default1():
    return send_node_maker('index.html')

@app.route('/ui/', methods=["GET"])
def send_node_maker_default():
    return send_node_maker('index.html')

@app.route('/ui/WIRP', methods=["GET"])
def send_node_maker_WIRP1():
    return send_node_maker('index.html')

@app.route('/ui/WIRP/', methods=["GET"])
def send_node_maker_WIRP():
    return send_node_maker('index.html')

@app.route('/ui/NodeMaker', methods=["GET"])
def send_node_maker_NMKR1():
    return send_node_maker('index.html')

@app.route('/ui/NodeMaker/', methods=["GET"])
def send_node_maker_NMKR():
    return send_node_maker('index.html')

@app.route('/ui/<path:path>')
def send_node_maker(path):
    # print ("UI PATH", path)
    filename = os.path.split(path)[-1]
    path = os.path.dirname(path)
    if filename in path or filename == path:
        filename = 'index.html'
    # print("PATH:", path, "  FILENAME:", filename)
    return send_from_directory(os.path.join('node-maker', path), filename)

@app.route('/ui/WIRP/<path:path>')
def send_node_maker_WIRP_files(path):
    # print ("UI PATH", path)
    filename = os.path.split(path)[-1]
    path = os.path.dirname(path)
    if filename in path or filename == path:
        filename = 'index.html'
    # print("PATH:", path, "  FILENAME:", filename)
    return send_from_directory(os.path.join('node-maker', path), filename)

@app.route('/ui/NodeMaker/<path:path>')
def send_node_maker_NodeMaker_files(path):
    # print ("UI PATH", path)
    filename = os.path.split(path)[-1]
    path = os.path.dirname(path)
    if filename in path or filename == path:
        filename = 'index.html'
    # print("PATH:", path, "  FILENAME:", filename)
    return send_from_directory(os.path.join('node-maker', path), filename)

@app.route(APP_ROOT + "publish", methods=["POST", "GET"])
@authorize
def publish_pipeline_route_no_slash():
    return publish_pipeline_route()

@app.route(APP_ROOT + "publish/", methods=["POST", "GET"])
@authorize
def publish_pipeline_route():
    pipeline = parse_url()

    # Check to make sure request has a valid key
    pipeline_settings = settings.get("PUBLISHED_PIPELINES", {})
    secret_key = pipeline_settings.get("secret_key", [])
    key = pipeline['url'].get("KEY", [""])[0]
    if key not in secret_key:
        return {"status": "Error", "message": "Need to provide a valid key as a query parameter to use this API: publish?KEY=<valid_key>"}

    service = pipeline["url"].get("SERVICE", [""])[0].upper()

    if service == "PUBLISH":
        response = publish_pipeline(pipeline["url"], LAYERS)
    elif service == "QUERY":
        response = query_pipeline(pipeline["url"], LAYERS)
    elif service == "REMOVE":
        response = remove_pipeline(pipeline["url"], LAYERS)
    else:
        response = "`{}` is an unrecognized service for this endpoint. ".format(
                pipeline["url"].get("SERVICE", "<Unspecified>")
            ) + """
            <p> This API supports the following SERVICE types </p>
            <p><ul>
                <li> publish?SERVICE=PUBLISH: Used to publish new pipelines </li>
                <li> publish?SERVICE=QUERY: Used to see what pipelines exist on the server </li>
                <li> publish?SERVICE=REMOVE: Used to remove a pipeline that exists on the server </li>
            </ul></p>
            <p> For help on any of these services, include "HELP" as one of the query parameters. E.g.
            publish?SERVICE=PUBLISH&HELP </p>
            """

    if not isinstance(response, dict):
        return response

    response = make_response(response)
    response.headers.set("Content-Type", "application/json")
    response.content_type = "application/json"
    response.mimetype = "application/json"
    return response


######################
# SERVER ENTRY POINT #
######################

if __name__ == "__main__":
    app.run(host="0.0.0.0")
