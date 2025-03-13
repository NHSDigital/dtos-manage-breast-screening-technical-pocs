POC four
========

We have a requirement to integrate with hospital hardware from our web application. [POC One](../poc_one/README.md) explored doing this from the browser using a browser extension to integrate with a 'gateway' server running within the hospital network. 

This POC has the gateway server polling a web API for messages which avoids the browser extension. We may need to do this as we're unsure if the browser extension would be allowed in trust IT policy. This approach would also allow us to initiate requests from triggers other than a user interaction. It may be that a combination of the two is ulimately required.

In this POC we list 'Appointment' instances within a clinic. The Appointment has state. When a user wants to send a participant to the modality we update the state of the Appointment and create a 'Message' in the DB. The polling gateway server picks up the message and sends it wherever it needs to go within the hospital.

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

#### Cons

* Constantly polling is inefficient
* Depending on the polling frequency it may be slower than the browser extension
* Probably not a good solution for image reading where even minor delays will cause a lot of user frustration

#### Prerequisites

* Python 3.13
* Pipenv
* Docker
* direnv

#### Running the POC

* Clone the repository
* Run `pipenv install` to install the dependencies
* Copy the .env.development to .env and edit if required. The defaults should be fine.
* `cd` into the `poc_four/manage_screening` directory
* Run `docker-compose up --build` to start the database and web app. This will also seed the DB with some demo data
* Open `http://localhost:8000/clinics` in a browser of your choice
* Open `http://localhost:8000/admin` in a separate tab. Usernamed 'admin' and password 'superuserpassword' (or whatever you set in the .env file)
* Click into the clinic and 'Send to Modality' on an appointment
* In the 'Messages' section of the admin interface you should see a new message. delivered_at and confirmed_atare both null. The message has not been picked up by a gateway
* In another terminal window `cd` into the `poc_four` directory
* Run `pipenv run python manage.py runserver` to start the gateway server
* The gateway will begin running and receive the first message which will be written to the terminal window. NB: The FHIR payload is representative and shouldn't be directly copied to our production implementation.
* The gateway will then poll every 1 second.
* In the interface send another appointment to the modality. The gateway will pick up the new message on it's next loop. 

The POC stops there. In production the gateway would send the payload to the destination within the message.
