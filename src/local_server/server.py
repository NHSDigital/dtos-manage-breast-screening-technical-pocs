from http.server import SimpleHTTPRequestHandler, HTTPServer
import os


class CustomHTTPRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path == '':
            self.path = '/index.htm'
        return super().do_GET()

    def do_POST(self):
        if self.path == '/do':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            print(post_data)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'POST request for ' + self.path.encode())


def run_server(port=9090, directory='.'):
    os.chdir(directory)  # Change the working directory to serve files from
    server_address = ('', port)
    httpd = HTTPServer(server_address, CustomHTTPRequestHandler)
    print(f"Serving on port {port}. Visit http://screening-gateway:{port}/")
    httpd.serve_forever()


if __name__ == "__main__":
    # Set the directory containing 'index.htm' and the port
    run_server(port=9090, directory='.')
