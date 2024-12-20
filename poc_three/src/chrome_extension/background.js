chrome.runtime.onMessage.addListener(async (message, sender, sendResponse) => {
  if (message.type === "postData") {
    console.log("Message received in background script:", message);

    // Return a Promise to handle the asynchronous operation
    return fetch("http://screening-gateway:9090/do", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(message.payload),
    })
      .then((response) => {
        if (response.ok) {
          console.log("Payload sent successfully from background script.");
          return { success: true, status: response.status };
        } else {
          console.error("Error sending payload:", response.statusText);
          return { success: false, status: response.status };
        }
      })
      .catch((error) => {
        console.error("Network error in background script:", error);
        return { success: false, error: error.message };
      });
    
  }
});
