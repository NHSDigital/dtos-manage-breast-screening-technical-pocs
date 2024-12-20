from http.server import SimpleHTTPRequestHandler, HTTPServer
import os
from jinja2 import Environment, FileSystemLoader

template_dir = Environment(loader=FileSystemLoader("./src/web_server"))


class CustomHTTPRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "":
            template = template_dir.get_template("index.htm")
            html_content = template.render()

            # Send response
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(html_content.encode("utf-8"))
        else:
            super().do_GET()


def run_server(port=8080, directory="."):
    os.chdir(directory)  # Change the working directory to serve files from
    server_address = ("", port)
    httpd = HTTPServer(server_address, CustomHTTPRequestHandler)
    print(f"Serving on port {port}. Visit http://localhost:{port}/")
    httpd.serve_forever()


if __name__ == "__main__":
    # Set the directory containing "index.htm" and the port
    run_server(port=8080, directory=".")
