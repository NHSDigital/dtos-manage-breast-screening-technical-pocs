POC five
========

We have a requirement to integrate with hospital hardware from our web application. [POC One](../poc_one/README.md) explored doing this from the browser using a browser extension to integrate with a 'gateway' server running within the hospital network. [POC Four](../poc_four/README.md) explored using HTTP polling to avoid the browser extension.

This POC replaces the HTTP polling approach with **Azure Relay** for real-time, bi-directional communication between the web application and gateway. This eliminates the inefficiency of constant polling while maintaining the benefits of avoiding browser extensions.

In this POC we list 'Appointment' instances within a clinic. The Appointment has state. When a user wants to send a participant to the modality we update the state of the Appointment and create a 'Message' in the DB. A separate process picks up messages from the database and sends them to the gateway via Azure Relay in real-time.

The Message has a payload, a destination and a type. In the example the type is 'FHIR' and the payload is FHIR, generated on the server. The destination would be configurable as it will vary from hospital to hospital. In this way we can support multiple message formats if we need to and keep all configuration in the web application rather than in the gateway where it is much more difficult to manage, test etc.

The messages also have `delivered_at` and `confirmed_at` dates. `delivered_at` is when the gateway requested the message and `confirmed_at` is set when the gateway receives the messages (it makes another POST request). We'll likely need to refine this but it's simple stab at being able to monitor the health of the gateway.

Some extra areas explored in this POC...

We don't currently have NHS design system components for Python. UI here has been built using Jinja2 macros based on the nunjucks from the design system. This is an approach we could expand on and seems to be relatively painless.

There is a basic start at how we might model the domain. It is very incomplete and slightly mixed up between the 'provider' and 'gateway' apps within 'manage_screening'.

The POC doesn't include any authentication by the gateway or encryption of the messages. We would certainly require authentication. Encryption could be just TLS or we could use the JWT signing/encryption or some variation of that depending the requirements when we look at assurance.

#### Pros

* No browser extension required
* Can be triggered by other events
* Message types and destinations configurable in the web application
* Simple gateway
* **Real-time communication via Azure Relay (no polling)**
* **Bi-directional communication for confirmations**
* **More efficient than HTTP polling**
* **Suitable for time-sensitive operations like image reading**

#### Cons

* Requires Azure Relay infrastructure
* More complex setup than simple HTTP polling
* Dependency on Azure services

#### Prerequisites

* Python 3.13
* Pipenv
* Docker
* direnv

#### Running the POC

* Clone the repository
* Run `pipenv install` to install the dependencies
* Copy the .env.development to .env and edit the Azure Relay configuration:
  * Set `AZURE_RELAY_SHARED_ACCESS_KEY` to your Azure Relay primary key
  * Update other Azure Relay settings if needed
* `cd` into the `poc_five/manage_screening` directory
* Run `docker-compose up --build` to start the database and web app. This will also seed the DB with some demo data
* Open `http://localhost:8000/clinics` in a browser of your choice
* Open `http://localhost:8000/admin` in a separate tab. Username 'admin' and password 'superuserpassword' (or whatever you set in the .env file)

##### Starting the Azure Relay Gateway

* In another terminal window `cd` into the `poc_five/gateway` directory
* Install gateway dependencies: `pip install -r requirements.txt`
* Set environment variables from the .env file or source them
* Run `python relay_listener.py` to start the Azure Relay gateway
* The gateway will connect to Azure Relay and wait for messages

##### Testing the Flow

* Click into the clinic and 'Send to Modality' on an appointment
* In the 'Messages' section of the admin interface you should see a new message with `delivered_at` and `confirmed_at` both null initially
* The message will be sent to the gateway via Azure Relay in real-time (no polling delay)
* The gateway will process the message and send confirmation back via HTTP
* Check the admin interface - `delivered_at` and `confirmed_at` should now be populated

The POC demonstrates real-time message delivery via Azure Relay. In production the gateway would send the payload to the actual hospital destination.
