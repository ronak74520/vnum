from http.server import HTTPServer
import sys
import os

sys.path.append(os.path.dirname(__file__))
from api.index import handler

if __name__ == "__main__":
    port = 5055
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, handler)
    print(f"[*] Vercel Local Server running on port {port}...")
    httpd.serve_forever()
