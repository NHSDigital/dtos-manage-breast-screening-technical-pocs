Screening Event Management - Technical POCs
===========================================

This repository contains the technical POCs for the Screening Event Management team. We are currently in alpha and looking at options for integrating with on site screening hardware, predominantly within radiology initially.

## Can we securely integrate with hardware from a browser

We have prior art of a 'gateway' machine running locally at screening sites and integrating with local PACS (Picture Archiving and Communication System) and RIS (Radiology Information System) systems. Activity on this gateway is automated/scheduled and is used for exporting data and images for research. Within screening, we have a user need to drive some of these integrations based on user actions in the screening management system.

### POCs

1. Create and sign the messages on the server and write them to the page when it is rendered. The message is then passed to the gateway via a browser extension when the user performs an action. [More...](./poc_one/README.md)

2. Open image reader applications using a link and a protocol handler. [More...](./poc_two/README.md)

3. Open image reader application using an XML-RPC call. [More...](./poc_three/README.md)   

4. Send and receive messages to a 'gateway' application using an API call. [More...](./poc_four/README.md)
