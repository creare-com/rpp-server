import base64
from hashlib import sha256
from flask import request, abort
from functools import wraps
from utils import _uppercase_for_dict_keys
from podpac import settings

def authorize(f):
    @wraps(f)
    def decorated_function(*args, **kws):
        auth = ["",""]
        key = [k for k in request.args.keys() if k.upper()=="TOKEN"]
        if len(key)>0:
            key=key[0]
        else:
            key="token"
        try:
            auth = request.headers.get("Authorization", request.args.get(key,"Basic :")).split("Basic ")[-1]
            if ":" not in auth:  # Probably base64 encoded
                auth = base64.b64decode(auth).decode('utf-8')
            auth = auth.split(':')
        except Exception as e:
            print ("Failed to parse authorization with error:", e)

        if len(auth)<2:
            auth=["",""]

        return f(*args, **kws)
    return decorated_function

def wrap_html_and_forward_auth_token(body):
    # This is the javascript that looks through all links in a document and appends the TOKEN query string parameters
    js = """
    <script>
    // Code partially borrowed from here: https://blog.miguelbernard.com/how-to-dynamically-add-a-query-string-to-all-links-in-a-page
    function fix_links(){
        var links = document.links;
        var curloc = window.location.origin;
        const newParams = new URLSearchParams();
        var params = (new URL(document.location)).searchParams;
        for (const [name, value] of params) {
            newParams.append(name.toLowerCase(), value);
        }
        var token = newParams.get('token');
        if (token === null){
            return;
        }
        for (var i=0; i < links.length; i ++) {
            var href = links[i].href;
            if (href) {
                try {
                    var url = new URL(href);
                    if(url.origin == curloc) {
                        url.searchParams.set("TOKEN", token);
                        links[i].href = url.href;
                    }
                }
                catch{}
            }
        }
    }
    fix_links();
    </script>
    """
    return """<html><head></head><body>{body}{js}</body></html>""".format(js=js, body=body)