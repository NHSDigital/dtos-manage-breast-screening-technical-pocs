from http.server import SimpleHTTPRequestHandler, HTTPServer
import os
from src.jwt_decoder import JWTDecoder
import urllib.parse
import json


class CustomHTTPRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "":
            self.path = "/index.htm"
        return super().do_GET()

    def do_POST(self):
        if self.path == "/do":
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)

            parsed_data = json.loads(post_data.decode('utf-8'))
            message = parsed_data.get('message', '')

            try:
                decoded_message = JWTDecoder().call(message)
                print("Decoded message: ", decoded_message)
                response_status = 200

            except ValueError as e:
                response_status = 400
                print(str(e), "Do nothing")

            self.send_response(response_status)
            self.end_headers()
            self.wfile.write(b"POST request for " + self.path.encode())


def run_server(port=9090, directory="."):
    os.chdir(directory)  # Change the working directory to serve files from
    server_address = ('', port)
    httpd = HTTPServer(server_address, CustomHTTPRequestHandler)
    print(f"Serving on port {port}. Visit http://screening-gateway:{port}/")
    httpd.serve_forever()


if __name__ == "__main__":
    # Set the directory containing 'index.htm' and the port
    run_server(port=9090, directory='.')
