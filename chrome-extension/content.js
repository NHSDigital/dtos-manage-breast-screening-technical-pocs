// Add an event listener to detect button clicks
document.addEventListener("click", (event) => {
  // Check if the clicked element is a button
  if (event.target.tagName.toLowerCase() === "button") {
    console.log("Button clicked:", event.target);

    // Example payload
    const payload = {
      buttonId: event.target.id || null,
      buttonText: event.target.innerText || "Unnamed button",
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
