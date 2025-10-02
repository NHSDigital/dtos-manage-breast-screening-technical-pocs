POC five
========

We have a requirement to integrate with hospital hardware from our web application. [POC One](../poc_one/README.md) explored doing this from the browser using a browser extension to integrate with a 'gateway' server running within the hospital network. [POC Four](../poc_four/README.md) explored using HTTP polling to avoid the browser extension.

This POC replaces the HTTP polling approach with **Azure Relay** for real-time, bi-directional communication between the web application and gateway. This eliminates the inefficiency of constant polling while maintaining the benefits of avoiding browser extensions.

In this POC we list 'Appointment' instances within a clinic. The Appointment has state. When a user wants to send a participant to the modality we update the state of the Appointment and create a 'Message' in the DB. A separate process picks up messages from the database and sends them to the gateway via Azure Relay in real-time. Each 'Provider' would have one (or more) 'Gateway' records and each record contains the relevant Relay config for that provider. The POC uses a thread to pick up the messages. This wouldn't be sufficient for production but we'd need some sort of background process outside of the main request. 

The Message has a payload, a destination and a type. In the example the type is 'FHIR' and the payload is FHIR, generated on the server. The destination would be configurable as it will vary from hospital to hospital. In this way we can support multiple message formats if we need to and keep all configuration in the web application rather than in the gateway where it is much more difficult to manage, test etc. NB The generated FHIR is made up and has not been checked for validity etc. It's just illustrative.

The messages also have `delivered_at` and `confirmed_at` dates. `delivered_at` is when the message is successfully sent and `confirmed_at` is set when the gateway receives the messages and sends confirmation back through the websocket.

In  [POC One](../poc_one/README.md) we used signed messages. We could still do that here but it's not been included in the PR. The Gateway does need a secret to connect to the Azure Relay socket so the connection is secured but we could still add the extra layer of integrity check (or encryption). 

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
* direnv (optional, for managing environment variables)
* Azure subscription (for creating Azure Relay resources)

#### Setting up Azure Relay

Before running the POC, you'll need to set up an Azure Relay Hybrid Connection:

1. **Create an Azure Relay Namespace:**
   * Log in to the [Azure Portal](https://portal.azure.com)
   * Click "Create a resource" and search for "Relay"
   * Click "Create"
   * Fill in the required details:
     * **Subscription**: Select your Azure subscription
     * **Resource group**: Create new or use existing
     * **Namespace name**: Choose a unique name (e.g., `my-relay-namespace`)
     * **Location**: Select a region close to you
     * **Pricing tier**: Standard (required for Hybrid Connections)
   * Click "Review + create" then "Create"
   * Wait for deployment to complete

2. **Create a Hybrid Connection:**
   * Navigate to your newly created Relay namespace
   * In the left menu, under "Entities", click "Hybrid Connections"
   * Click "+ Hybrid Connection"
   * Enter a name for your hybrid connection
   * Leave "Requires Client Authorization" checked
   * Click "Create"

3. **Get the Connection Details:**
   * Click on your hybrid connection name
   * Click "Shared access policies" in the left menu
   * Click on the "RootManageSharedAccessKey" policy
   * Copy the following values (you'll need them for the .env file):
     * **Primary Key** - this is your `AZURE_RELAY_SHARED_ACCESS_KEY`
   * Go back to the hybrid connection overview page
   * Note down:
     * Your namespace name
     * Your hybrid connection name

#### Environment Variables Setup

The POC requires several environment variables to be configured:

1. **Copy the example environment file:**
   
   ```bash
   cp .env.development .env
   ```
   
2. **Edit the `.env` file and update the following variables:**

   **Database Configuration (defaults should work fine):**

   ```
   POSTGRES_DB=pgdb
   POSTGRES_USER=pguser
   POSTGRES_PASSWORD=pgpassword
   DJANGO_SUPERUSER_PASSWORD=superuserpassword
   ```

   **Gateway Configuration:**
   ```
   GATEWAY_ID=d4679168-3a52-4e96-985d-1e6bb299f6f2
   ```
   This is a UUID identifying the gateway. You can generate a new one or use the default.

   **Azure Relay Configuration (REQUIRED):**
   ```
   AZURE_RELAY_NAMESPACE=your-namespace.servicebus.windows.net
   AZURE_RELAY_HYBRID_CONNECTION=your-hybrid-connection-name
   AZURE_RELAY_KEY_NAME=RootManageSharedAccessKey
   AZURE_RELAY_SHARED_ACCESS_KEY=your_primary_key_from_azure
   ```
   Replace the values with the details from your Azure Relay setup above.

   **Django Configuration:**
   ```
   DJANGO_BASE_URL=http://localhost:8000
   ```
   This is the base URL for the Django application, used for the gateway to send confirmations back.

3. **Source the environment variables** (if using direnv, this happens automatically):
   ```bash
   export $(cat .env | xargs)
   ```

#### Running the POC

* Clone the repository
* Run `pipenv install` to install the dependencies
* Set up Azure Relay as described above
* Configure environment variables as described above
* `cd` into the `poc_five/manage_screening` directory
* Run `docker-compose up --build` to start the database and web app. This will also seed the DB with some demo data
* Open `http://localhost:8000/clinics` in a browser of your choice
* Open `http://localhost:8000/admin` in a separate tab. Username 'admin' and password 'superuserpassword' (or whatever you set in the .env file)

##### Starting the Azure Relay Gateway

* In another terminal window `cd` into the `poc_five/gateway` directory
* Install gateway dependencies: `pip install -r requirements.txt`
* Set environment variables from the .env file:
  ```bash
  cd ../
  export $(cat .env | xargs)
  cd gateway
  ```
* Run `python relay_listener.py` to start the Azure Relay gateway
* The gateway will connect to Azure Relay and wait for messages
* You should see output indicating successful connection: `Relay listener started. Listening for messages...`

##### Testing the Flow

* Click into the clinic and 'Send to Modality' on an appointment
* In the 'Messages' section of the admin interface you should see a new message with `delivered_at` and `confirmed_at` both null initially
* The message will be sent to the gateway via Azure Relay in real-time (no polling delay)
* The gateway will log the received message to the console
* The gateway will process the message and send confirmation back via HTTP to the Django application
* Check the admin interface - `delivered_at` and `confirmed_at` should now be populated

The POC demonstrates real-time message delivery via Azure Relay with bi-directional communication. In production the gateway would send the payload to the actual hospital destination (e.g. Trust integration engine, PACS etc.) and return notifications in the opposite direction

#### Troubleshooting

* **Gateway can't connect to Azure Relay**: Check that your `AZURE_RELAY_SHARED_ACCESS_KEY` is correct and that the namespace and hybrid connection names match your Azure configuration

* **Messages not being delivered**: Ensure the gateway is running and connected before sending messages from the web application

  
