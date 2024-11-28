from http.server import SimpleHTTPRequestHandler, HTTPServer
import os


class CustomHTTPRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path == '':
            self.path = '/index.htm'
        return super().do_GET()


def run_server(port=8080, directory='.'):
    os.chdir(directory)  # Change the working directory to serve files from
    server_address = ('', port)
    httpd = HTTPServer(server_address, CustomHTTPRequestHandler)
    print(f"Serving on port {port}. Visit http://manage-breast-screening:{port}/")
    httpd.serve_forever()


if __name__ == "__main__":
    # Set the directory containing 'index.htm' and the port
    run_server(port=8080, directory='.')
