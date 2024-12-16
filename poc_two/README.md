POC two
=======

We have a user need to open DICOM studies in an external viewer. This is currently done in the NBSS application by shelling out to either an `exe` or `com` component installed on the same machine as the NBSS application and the viewer application. If we're to use a browser based application to do this than that presents some problems.

In this POC we use a protocol handler and hyperlink. This is supported by some viewer applications and allows us to pass querystring parameters, in this example the accession number, to the viewer and have it open the referenced study. 

In practice we may want to open the viewer application in response to a page load rather than a link/button click but this could easily be adapted to do that instead.

The example uses the Horos open source DICOM viewer.

### Pros

* Simple
* Doesn't require extra software on the machine or the network

### Cons

* not universally supported
* does not receive any confirmation from the viewer that the process worked (or didn't)
* It may be tricky to know from the browser whether there is a viewer application on the machine.

### Prerequisites

* Python 3.6
* pipenv
* Browser
* [Horos DICOM viewer](https://horosproject.org)

#### Installation

* Add the example images to Horos (drag them onto the database window)
* Clone the repository
* Run `pipenv install` to install the dependencies
* `cd` into the `poc_two` directory
* `pipenv run python -m src.web_server.server`
* Open a web browser and navigate to `http://localhost:8080` and you should see the web server running
* Click the "View study in image reader" link
* The study for "Hazel Brooke Connelly" should open
