from http.server import SimpleHTTPRequestHandler, HTTPServer
import os
import json
import requests


class CustomHTTPRequestHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == "":
            self.path = "/index.htm"
        return super().do_GET()

    def do_POST(self):
        if self.path == "/do":
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)

            # parse the postdata string as json
            parsed_post_data = json.loads(post_data.decode("utf-8"))
            parsed_message = json.loads(parsed_post_data["message"])

            print("parsed POST message: ", parsed_message)
            print("message type: ", parsed_message["type"])
            print("message payload: ", parsed_message["payload"])
            print("message destination: ", parsed_message["destination"])

            payload = parsed_message["payload"]
            destination = parsed_message["destination"]

            response = self.send_XML_RPC_request(payload, destination)

            response_status = 200
            self.send_response(response_status)
            self.end_headers()
            self.wfile.write(b"POST request for " + self.path.encode())

    def send_XML_RPC_request(self, xml_message, destination):
        print("Sending XML-RPC request to ", destination)
        headers = {"Content-Type": "text/xml"}
        response = requests.post(destination, data=xml_message, headers=headers)
        print("Response: ", response.text)
        return response



def run_server(port=9090, directory="."):
    os.chdir(directory)  # Change the working directory to serve files from
    server_address = ('', port)
    httpd = HTTPServer(server_address, CustomHTTPRequestHandler)
    print(f"Serving on port {port}. Visit http://screening-gateway:{port}/")
    httpd.serve_forever()


if __name__ == "__main__":
    # Set the directory containing 'index.htm' and the port
    run_server(port=9090, directory='.')
