from collections import OrderedDict
import json

from flask import request, make_response

import podpac
from podpac import settings

from utils import _string_to_html

def publish_pipeline(url, LAYERS):
    """
    # Adds a pipeline to the UDP server

    This API returns error messages when parameters are incorrect.

    Both GET and POST requests can be used. In both cases the url needs the following query parameters:

    * SERVICE=PUBLISH
    * NAME=`<desired name of published pipeline>`
    * KEY=`<secret key present on the server>`, that is, a key present in `podpac.settings["PUBLISHED_PIPELINES"]["secret_key"]`

    Optional parameters include:

    * EXPIRES=`<date when pipeline expires in format YYYY-MM-DD>`

    For the GET request, add the `DATA=<json definition of podpac pipeline>` query parameter in the url.

    For the POST request, give the string version of the JSON definition of the pipeline as the payload.

    Examples
    ----------

    Example URL for publishing a pipeline using a GET request:

    ```
    https://<server_url>/api/publish/?SERVICE=PUBLISH&name=myPipeName&key=<valid_key>&data={"Arange":{"node":"core.algorithm.utility.Arange"}}
    ```

    Some of these definitions can exceed the URL length, in that case you can do a POST request instead. E.g., in Python:

    ```python
    import requests
    requests.post(
        'https://<server_url>/api/publish/?SERVICE=PUBLISH&name=myPipeName&key=<valid_key>',
        data='{"Arange":{"node":"core.algorithm.utility.Arange"}
    )
    ```

    Notes
    ---------
    To create the JSON pipeline definitions, use the open source <a href="https://podpac.org">PODPAC library</a>.
    """
    try:
        pipeline_settings = settings.get("PUBLISHED_PIPELINES", {})
        layers = LAYERS._layers
        # This is for security
        try:
            secret_key = pipeline_settings["secret_key"]
        except KeyError:
            response = {
                "status": "Error",
                "message": "Pipeline could not be published because server does not have an authentication key set up.",
            }
            return response
        url_key = url["KEY"][0]
        assert url_key in secret_key

        if "NAME" not in url or "HELP" in url:
            return _string_to_html(publish_pipeline.__doc__)

        name = url["NAME"][0]

        if name in layers:
            message = "Updated previously published pipeline: `{name}`."
        else:
            message = "Published pipeline: `{name}`."

        try:
            json_data = url.get("DATA", [request.data.decode("utf8")])[0]
            data = json.loads(json_data, object_pairs_hook=OrderedDict)
        except:
            response = {
                "status": "Error",
                "message": "No valid json-formatted data was returned for this pipeline.",
            }
            return response

        try:
            # print(json_data)
            n = podpac.Node.from_json(json_data)
        except Exception as e:
            # print("adding failed")
            response = {
                "status": "Error",
                "message": "Invalid pipeline defintion specified. Error when trying to create Node: {}".format(
                    e
                ),
            }
            return response

        LAYERS.set(
            name,
            {
                "author_key": url_key,
                "definition": n.definition,
                "expiration": url.get("Expires", [None])[0],
            },
        )
        response = {"status": "Success", "message": message.format(name=name)}
    except AssertionError as e:
        response = {
            "status": "Error",
            "message": "Pipeline could not be published because publishing key does not match server key.",
        }
    except Exception as e:
        response = {
            "status": "Error",
            "message": "Pipeline could not be published with error: {error}".format(error=str(e)),
        }
    return response


def query_pipeline(url, LAYERS):
    """
    # Queries an existing pipeline.

    GET requests can be used with the following parameters:

    * SERVICE=QUERY
    * NAME=`<desired name of published pipeline>`, if empty, all pipelines associated with this KEY will be returned
    * KEY=`<secret key present on the servers>`, that is, a key present in `podpac.settings["PUBLISHED_PIPELINES"]["secret_key"]`
    * VERBOSE: If present, more detailed data bout the pipeline will be returned:
        * The return will then also contain the "coordinates" entries that give the native coordinates for each pipeline
        * The return will then also contain the "outputs" entries that give the name of bands for each pipeline


    Examples
    ----------

    Example URL to query a pipeline:

    ```
    https://<server_url>/api/publish/?SERVICE=QUERY&name=myPipeName&key=<valid_key>
    ```

    Example URL to get all pipelines posted by this secretkey:

    ```
    https://<server_url>/api/publish/?SERVICE=QUERY&key=<valid_key>
    ```
    """
    try:
        if "HELP" in url:
            return _string_to_html(query_pipeline.__doc__)
        pipeline_settings = settings.get("PUBLISHED_PIPELINES", {})
        layers = LAYERS._layers
        # This is for security
        try:
            secret_key = pipeline_settings["secret_key"]
        except KeyError:
            response = {
                "status": "Error",
                "message": "Pipeline could not be published because server does not have an authentication key set up.",
            }
            return response
        url_key = url["KEY"][0]
        assert url_key in secret_key

        if "HELP" in url:
            return _string_to_html(query_pipeline.__doc__)

        name = url.get("NAME", [None])[0]

        response = {"status": "Success"}
        if name is None or name == '':
            response.update(
                {
                    "message": "Returning all pipelines defined using the provided secret key.",
                    "pipelines": {
                        k: v["definition"] for k, v in layers.items() if v["author_key"] == url_key
                    },
                }
            )
        elif name in layers:
            response.update(
                {
                    "message": "Returning defintion for pipeline `{}`.".format(name),
                    "definition": layers[name]["definition"],
                }
            )
        else:
            response.update({
                "status": "Error",
                "message": "No pipeline with name `{}` defined on server.".format(name)
            })
        if "VERBOSE" in url:
            # need to actually instantiate instances of the nodes
            nodes = None
            if name is None or name == '':
                nodes = {k: podpac.Node.from_definition(v) for k, v in response['pipelines'].items()}
            else:
                nodes = {name: podpac.Node.from_definition(response["definition"])}

            details = {
                "coordinates": {k: _find_node_coordinates(n) for k, n in nodes.items()},
                "outputs": {k: getattr(n, 'outputs', None)for k, n in nodes.items()},
                "test":"1"
                }
            from server import DEFAULT_COORDS  # Have to do it here because of circular imports
            details["coordinates"]['_default_'] = DEFAULT_COORDS().definition

            response.update(details)
    except AssertionError as e:
        response = {
            "status": "Error",
            "message": "Pipeline(s) could not be queried because publishing key does not match server key.",
        }
    except Exception as e:
        response = {
            "status": "Error",
            "message": "Pipeline(s) could not be queried with error: {error}".format(error=str(e)),
        }
    response = json.dumps(response, cls=podpac.core.utils.JSONEncoder)
    response = make_response(response)
    response.headers.set("Content-Type", "application/json")
    response.content_type = "application/json"
    response.mimetype = "application/json"
    return response


def _find_node_coordinates(node):
    try:
        coords = [c.definition for c in node.find_coordinates()]
    except Exception as e:
        print(e)
        coords = None
    return coords


def remove_pipeline(url, LAYERS):
    """
    # Removes an existing pipeline

    GET requests can be used:

    * SERVICE=REMOVE
    * NAME=`<desired name of pipeline to remove>`
    * KEY=`<secret key present on the servers>`, that is, a key present in `podpac.settings["PUBLISHED_PIPELINES"]["secret_key"]`


    Examples
    ----------

    Example URL to remove a pipeline:

    ```
    https://<server_url>/api/publish/?SERVICE=REMOVE&name=myPipeName&key=<valid_key>
    ```
    """
    try:
        pipeline_settings = settings.get("PUBLISHED_PIPELINES", {})
        layers = LAYERS._layers
        # This is for security
        try:
            secret_key = pipeline_settings["secret_key"]
        except KeyError:
            response = {
                "status": "Error",
                "message": "Pipeline could not be removed because server does not have an authentication key set up.",
            }
            return response
        url_key = url["KEY"][0]
        assert url_key in secret_key

        if "NAME" not in url or "HELP" in url:
            return _string_to_html(remove_pipeline.__doc__)

        name = url.get("NAME", [None])[0]

        if name in layers and url_key == layers[name]["author_key"]:
            response = {
                "status": "Success",
                "message": "Pipeline `{}` was sucessfully removed.".format(name),
            }
            LAYERS.remove(name)
        else:
            response = {
                "status": "Error",
                "message": "Pipeline `{}` could not be removed.".format(name),
            }

    except AssertionError as e:
        response = {
            "status": "Error",
            "message": "Pipeline could not be removed because publishing key does not match server key.",
        }
    except Exception as e:
        response = {
            "status": "Error",
            "message": "Pipeline could not be removed with error: {error}".format(error=str(e)),
        }
    return response