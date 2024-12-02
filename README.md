Screening Event Management - Technical POCs
===========================================

This repository contains the technical POCs for the Screening Event Management team. We are currently in alpha and looking at options for integrating with on site screening hardware, predominantly within radiology initially.

## Can we securely integrate with hardware from a browser

We have prior art of a 'gateway' machine running locally at screening sites and integrating with local PACS (Picture Archiving and Communication System) and RIS (Radiology Information System) systems. Activity on this gateway is automated/scheduled and is used for exporting data and images for research. Within screening, we have a user need to drive some of these integrations based on user actions in the screening management system.

### POC One

Create and sign the messages on the server and write them to the page when it is rendered. The message is then passed to the gateway via a browser extension when the user performs an action.

Creating the message on the remote server allows the browser extension and to a lesser extent the gateway to be pretty dumb. We can keep any message customisation that we require on the server to avoid having to do too much configuration locally at the sites. This will also allow us to sign the message with a private key held securely and then distribute a public key with the gateway deployment without having to worry about securing that at the site.

In this example we create and sign a javascript web token (JWT) on the application server hosting the manage application. This is written to the page that is returned to the browser. The extension passes the JWT to the gateway which validates the signature and logs the message to the console.

#### Pros

* Secure - the message is cryptographically signed so cannot be forged or tampered with and can be simply secured in transit over HTTPS
* Simple - uses common technology that is well supported
* Can be supported in 'enterprise' environments. Both Google and Microsoft have mechanisms for deploying extensions to their browsers in a managed way and supported by policy.

#### Cons
* Requires a browser extension to be installed which may be controversial
* Puts us a little bit at the mercy of the browser vendors. Breaking changes are not uncommon in extension APIs and the updates would be out of our control at the screening sites.

The following instructions should work on OS X and Linux. If you are using Windows, you may need to adapt the instructions and if you do then a PR with a windows version of these docs would be most welcome.

#### Prerequisites

* Python 3.6
* pipenv
* Google Chrome
* openssl

#### Installation

* Clone the repository
* Run `pipenv install` to install the dependencies
* Generate a key pair in the directory
    * `openssl genrsa -out private.pem 4096`
    * `openssl rsa -in private.pem -pubout -out public.pem`
* Add the extension to Google Chrome ([follow these instructions](https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world#load-unpacked)
* Add the following entries to your `/etc/hosts` file. This isn't strictly necessary as the web server and the gateway run on different ports but it makes it easier to demonstrate if we use these host names instead of localhost.
    ```
    127.0.0.1 manage-breast-screening
    127.0.0.1 screening-gateway
    ```
* In a terminal window copy the private key into an environment variable and then run the web server with 
    ```
    export JWT_PRIVATE_KEY=$(cat private.pem)
    pipenv run python -m src.web_server.server
    ```
* In another terminal session copy the public key into the environment and run the gateway with 
    ```
    export JWT_PUBLIC_KEY=$(cat public.pem)
    pipenv run python -m src.screening-gateway.server
    ```
* Open Google Chrome and navigate to `manage-breast-screening:8080` and you should see the web server running
* Clicking either of the "Send for scan" buttons will send a message to the gateway which will log a message to the console
