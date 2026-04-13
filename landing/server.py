import http.server
import os

port = int(os.environ.get("PORT", 3000))
handler = http.server.SimpleHTTPRequestHandler
handler.extensions_map.update({".html": "text/html"})

with http.server.HTTPServer(("0.0.0.0", port), handler) as httpd:
    print(f"Landing server on port {port}")
    httpd.serve_forever()
