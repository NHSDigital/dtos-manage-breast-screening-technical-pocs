// Add an event listener to detect button clicks
document.addEventListener("click", (event) => {
  // Check if the clicked element is a button
  if (event.target.hasAttribute("data-open-reader")) {
    event.preventDefault();
    console.log("Button clicked:", event.target);

    const payload = {
      message: event.target.dataset.gatewayMessage,
      timestamp: new Date().toISOString(),
    };

    // Send the payload to the background script
    chrome.runtime.sendMessage(
      {
        type: "postData",
        payload: payload,
      },
    ).then(
      (response) => {
        console.log("Response from background script:", response);
      }
    );
  }
});
