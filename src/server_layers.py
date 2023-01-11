import os
import json
from collections import OrderedDict
from typing import OrderedDict
import traitlets as tl
import datetime
import numpy as np

import ogc
import podpac
from ogc.podpac import Layer as OGCLayer0
from podpac.core.authentication import S3Mixin
from podpac import Node

def home(ogc):
    """
    """
    return """
    <h4>RPP OGC Server</h4>
    <ul>
        <li> WCS: Open Geospatial Consortium (OGC) Web Coverage Service (WCS) <i>(v1.0.0)</i>
        <ul>
            <li><a href="?SERVICE=WCS&REQUEST=GetCapabilities&VERSION=1.0.0">WCS GetCapabilities (XML)</a> <i>(v1.0.0)</i></li>
            <li><a href="?SERVICE=WCS&REQUEST=DescribeCoverage&VERSION=1.0.0&COVERAGE={test_layer}">WCS DescribeCoverage Example (XML)</a> <i>(v1.0.0)</i></li>
            <li><a href="?SERVICE=WCS&VERSION=1.0.0&REQUEST=GetCoverage&FORMAT=GeoTIFF&COVERAGE={test_layer}&BBOX=-132.90225856307210961,23.62932030249929483,-53.60509752693091912,53.75883389158821046&CRS=EPSG:4326&RESPONSE_CRS=EPSG:4326&WIDTH=346&HEIGHT=131">WCS GetCoverage Example (GeoTIFF)</a> <i>(v1.0.0)</i></li>
            <li><a href="?SERVICE=WCS&VERSION=1.0.0&REQUEST=GetCoverage&FORMAT=GeoTIFF&COVERAGE={test_layer_time}&BBOX=34.3952751159668,38.26394082159894,34.398660063743584,38.26779045113519&CRS=EPSG:4326&RESPONSE_CRS=EPSG:4326&WIDTH=631&HEIGHT=914&TIME=2021-03-01T12:00:00.000Z">WCS GetCoverage Example (GeoTIFF)</a> dynamic layer <i>(v1.0.0)</i></li>
        </ul>
        </li>
        <li> WMS: Open Geospatial Consortium (OGC) Web Map Service (WMS) <i>(v1.3.0)</i>
        <ul>
            <li><a href="?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0">WMS GetCapabilities (XML)</a> <i>(v1.3.0)</i></li>
            <li><a href="?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS={test_layer}&STYLES=&FORMAT=image%2Fpng&TRANSPARENT=true&HEIGHT=256&WIDTH=256&CRS=EPSG%3A3857&BBOX=-10018754.171394622,2504688.5428486555,-7514065.628545966,5009377.08569731">WMS GetMap Example (PNG)</a> <i>(v1.3.0)</i></li>
            <li><a href="?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0&LAYERS={test_layer_time}&STYLES=&FORMAT=image%2Fpng&TRANSPARENT=true&HEIGHT=256&WIDTH=256&CRS=EPSG%3A3857&BBOX=-10018754.171394622,2504688.5428486555,-7514065.628545966,5009377.08569731&TIME=2021-03-01T12:00:00.000Z">WMS GetMap Example (PNG)</a> dynamic layer <i>(v1.3.0)</i></li>
            <li><a href="?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetLegendGraphic&LAYER={test_layer}&STYLE=default&FORMAT=image/png">WMS GetLegend Example (PNG)</a> <i>(v1.3.0)</i></li>
        </ul>
        </li>
    </ul>
    """.format(test_layer="TestLayer", test_layer_time="TestLayer")

def _update_key(key:str, source:dict, dest:dict):
    # print(key, source, dest)
    if isinstance(source[key], dict) and key in dest:
        for key2 in source[key]:
            # print(key2)
            dest[key] = _update_key(key2, source[key], dest[key])
    else:
        # print(key, source, dest)
        dest[key] = source[key]
    return dest

class OGCLayer(OGCLayer0):
    valid_times = tl.List(trait=tl.Instance(datetime.date), default_value=tl.Undefined, allow_none=True)
    def get_node(self, args):
        definition = self.node.definition
        # print ("Pre DEF", definition, args.get("PARAMS"))
        params = json.loads(args.get("PARAMS", "{}"))
        if "INTERPOLATION" in args:
            attrs = params.get('attrs', {})
            attrs['interpolation'] = args["INTERPOLATION"]
            params['attrs'] = attrs

        base = [k for k in definition.keys() if k != "podpac_version"][-1]
        for key in params:
            definition[base] = _update_key(key, params, definition[base])
        # print ("Post DEF", definition)
        node = Node.from_definition(definition)
        print(node.json_pretty)
        return node

class Layers(tl.HasTraits):
    source = tl.Unicode()
    s3 = tl.Any()
    default_times = tl.Any()
    default_grid_coordinates = tl.Instance(ogc.GridCoordinates)
    _ogc_layers_cache = tl.Dict()
    convert_requests_to_default_crs = tl.Bool(True)
    skip_failed = tl.Bool(False)
    persistent_layers = tl.List()

    @tl.default("s3")
    def _default_s3(self):
        return (
            S3Mixin().s3
        )  # This will automatically pull credentials from aws config OR podpac settings

    @property
    def _layers(self):
        """ Need to read every time in case the file changes """
        try:
            if self.source.startswith("s3://"):
                data = self.s3.open(self.source, "r").read()
            else:
                data = open(self.source, "r").read()
            return json.loads(data, object_pairs_hook=OrderedDict)
        except:
            if not self.source.startswith("s3://") and not os.path.exists(self.source):
                open(self.source, "w").write(json.dumps({}))
            return {}

    def get(self, key, default=None):
        return self._layers.get(key, default)

    def set(self, key, item, clear_cache=True):
        layers = self._layers
        layers[key] = item
        self.update(layers)
        if clear_cache and key in self._ogc_layers_cache:
            del self._ogc_layers_cache[key]

    def remove(self, key):
        layers = self._layers
        del layers[key]
        self.update(layers)

    def update(self, layers):
        data = json.dumps(layers)
        if self.source.startswith("s3://"):
            with self.s3.open(self.source, "w") as file:
                file.write(data)
        else:
            with open(self.source, "w") as file:
                file.write(data)

    @property
    def ogc_layers(self):
        """
        Returns the OGC Layers which are created as part of the OGC package.
        This structure is needed for WMS/WCS requests
        """
        # Remove any part of the cache that's no longer needed
        # i.e. when a layer was removed.
        kwargs = {}
        ogc_layers = []
        # Remove any part of the cache that's no longer needed
        # i.e. when a layer was removed.
        layers = self._layers
        keys = list(self._ogc_layers_cache.keys())
        for key in keys:
            if (key not in layers) or (self._ogc_layers_cache[key]['definition'] != layers[key]['definition']):
                del self._ogc_layers_cache[key]

        # Make the OGC layers
        for layer in layers:
            l = None
            if layer in self._ogc_layers_cache:
                l = self._ogc_layers_cache[layer]['node']
            elif not self.skip_failed:
                try:
                    l = self.make_ogc_layer(layer, layers[layer])
                except Exception as e:
                    print ("Exception creating ogc layer:", type(e), e)
                    continue
                self._ogc_layers_cache[layer] = {"definition": layers[layer]["definition"], "node": l}
            if l is not None:
                ogc_layers.append(l)

        return self.persistent_layers + ogc_layers

    def make_ogc_layer(self, name, layer, abstract=""):
        node = Node.from_json(json.dumps(layer["definition"]))
        coords = node.find_coordinates()
        kwargs = {}
        if len(coords) == 1:
            try:
                coords = coords[0]
                if "time" in coords.udims:
                    dt = coords['time'].coordinates.astype(object).tolist()
                    kwargs["valid_times"] = dt
                    # Need to drop time, otherwise podpac won't give us a geotransform.
                    coords = coords.udrop('time')

                gt = coords.geotransform
                gc = ogc.GridCoordinates(
                    geotransform=gt,
                    x_size=coords["lon"].size,
                    y_size=coords["lat"].size
                )
                kwargs["grid_coordinates"] = gc

            except Exception as e:
                # No geotransform -- my guess
                print(e)

        if node.style.name:
            title = node.style.name
        else:
            title = name

        abstract = layer.get("abstract", "")

        ogc_layer = OGCLayer(
            identifier=name,
            title=title,
            node=node,
            abstract=abstract,
            convert_requests_to_default_crs=self.convert_requests_to_default_crs,
            **kwargs
            )
        return ogc_layer


