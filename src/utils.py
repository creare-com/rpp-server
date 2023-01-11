from collections import OrderedDict

import markdown
from six import string_types
import json

import urllib.parse as urllib
from flask import request

from podpac.core.utils import _get_param


def _uppercase_for_dict_keys(lower_dict):
    upper_dict = {}
    for k, v in lower_dict.items():
        if isinstance(v, dict):
            v = _uppercase_for_dict_keys(v)
        upper_dict[k.upper()] = v
    return upper_dict

def _string_to_html(string):
    return markdown.markdown(string.replace('\n    ', '\n'))

def default_pipeline(pipeline=None):
    """Get default pipeline definition, merging with input pipline if supplied

    Parameters
    ----------
    pipeline : dict, optional
        Input pipline. Will fill in any missing defaults.

    Returns
    -------
    dict
        pipeline dict
    """
    defaults = {
        "pipeline": {},
        "settings": {},
        "output": {"format": "netcdf", "filename": None, "format_kwargs": {}},
        # API Gateway
        "url": "",
        "params": {},
    }

    # merge defaults with input pipelines, if supplied
    if pipeline is not None:
        pipeline = {**defaults, **pipeline}
        pipeline["output"] = {**defaults["output"], **pipeline["output"]}
        pipeline["settings"] = {**defaults["settings"], **pipeline["settings"]}
    else:
        pipeline = defaults

    # overwrite certain settings so that the function doesn't fail
    pipeline["settings"]["ROOT_PATH"] = "/tmp"
    pipeline["settings"]["LOG_FILE_PATH"] = "/tmp/podpac.log"

    return pipeline


def parse_url():
    """Parse pipeline, settings, and output details from event depending on trigger

    Parameters
    ----------
    """

    pipeline = default_pipeline()
    url = request.args.to_dict(flat=False)

    url = _uppercase_for_dict_keys(url)
    pipeline["url"] = url
    if isinstance(pipeline["url"], string_types):
        pipeline["url"] = urllib.parse_qs(urllib.urlparse(pipeline["url"]).query)

    # These are parameters not part of the OGC spec, which are stored in the "PARAMS" variable (which is part of the spec)
    pipeline["params"] = url.get("PARAMS")
    if isinstance(pipeline["params"], string_types):
        pipeline["params"] = json.loads(pipeline["params"], object_pairs_hook=OrderedDict)

    # TODO: This next line was added for debugging
    # TODO: Determine if we actually need this section of code
    pipeline["params"] = None
    if pipeline["params"]:
        # make all params lowercase
        pipeline["params"] = [param.lower() for param in pipeline["params"]]

        # look for specific parameter definitions in query parameters, these are not part of the OGC spec
        for param in pipeline["params"]:
            # handle SETTINGS in query parameters
            if param == "settings":
                # Try loading this settings string into a dict to merge with default settings
                try:
                    api_settings = pipeline["params"][param]
                    # If we get here, the api settings were loaded
                    pipeline["settings"] = {**pipeline["settings"], **api_settings}
                except Exception as e:
                    print("Got an exception when attempting to load api settings: ", e)
                    print(pipeline)

            # handle OUTPUT in query parameters
            elif param == "output":
                pipeline["output"] = pipeline["params"][param]
            # handle FORMAT in query parameters
            elif param == "format":
                pipeline["output"]["format"] = _get_param(pipeline["params"], param).split("/")[-1]
                # handle image returns
                if pipeline["output"]["format"] in ["png", "jpg", "jpeg"]:
                    pipeline["output"]["format_kwargs"]["return_base64"] = True

    # Check for the FORMAT QS parameter, as it might be part of the OGC spec
    for param in pipeline["url"]:
        if param.lower() == "format":
            pipeline["output"][param.lower()] = _get_param(pipeline["url"], param).split("/")[-1]
            # handle image returns
            # if pipeline["output"]["format"] in ["png", "jpg", "jpeg"]:
            #     pipeline["output"]["format_kwargs"]["return_base64"] = True

    return pipeline