POC three
=======

We have a user need to open DICOM studies in an external viewer. This is currently done in the NBSS application by shelling out to either an `exe` or `com` component installed on the same machine as the NBSS application and the viewer application. If we're to use a browser based application to do this than that presents some problems.

In this POC we use the chrome extension/gateway setup from [poc one](../poc_one/) to send an XML-RPC message to the PAC viewer application. The viewer application then opens the study in the viewer.

The example uses the Horos open source DICOM viewer.

### Pros

* Doesn't need to be on the same machine as the viewer application
* Will receive a response from the viewer application so we can know if the process worked or not
* Could be used to detect if there is a viewer application allowing us to inform the user

### Cons

* not universally supported
* will require a gateway to be installed on the local network. While this isn't strictly true as we could probably send the message direct from a browser extension, that would be difficult to do securely.

### Prerequisites

* Python 3.6
* pipenv
* Browser
* [Horos DICOM viewer](https://horosproject.org)

#### Installation

* Add the example images to Horos (drag them onto the database window)
* Clone the repository
* Run `pipenv install` to install the dependencies
* `cd` into the `poc_three` directory
* `pipenv run python -m src.web_server.server`
* In another terminal window... `pipenv run python -m src.screening-gateway.server`
* Open a web browser and navigate to `http://localhost:8080` and you should see the web server running
* Click the "View study in image reader" link
* The study for "Hazel Brooke Connelly" should open
