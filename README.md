# **Slack Assistant Bot with Image Generation**
## **Description**
The Slack Assistant Bot with Image Generation is a powerful AI-driven chatbot that helps users with various tasks within a Slack workspace. Powered by OpenAI GPT-3.5-turbo, the bot can understand and respond to user messages, as well as generate, edit, and create variations of images based on user prompts.
## **Features**
- Text-based conversation with users in the Slack workspace.
- Image generation based on textual descriptions.
- Image editing using textual prompts and an image mask.
- Image variation creation from a given image.
- Supports both direct messages and public channels.
## **Requirements**
- Python 3.7 or higher
- OpenAI Python package
- Slack Bolt and Socket Mode packages
- An OpenAI API key
- Slack App and Bot tokens
## **Setup**
1. Clone the repository to your local machine.
1. Install the required Python packages: pip install -r requirements.txt
1. Replace the SLACK\_APP\_TOKEN, SLACK\_BOT\_TOKEN, and openai.api\_key variables with your respective tokens and keys.
1. Run the main.py script: python main.py
## **Usage**
### **General conversation**
The bot can be used for general conversation and assistance within a Slack workspace. You can interact with the bot through direct messages or by mentioning the bot in public channels using the format <@bot\_user\_id>.
### **Image generation**
To generate an image, send a message to the bot with a description of the image you want. The bot will understand the request, improve and translate the prompt to English, and generate the image(s) accordingly. The response format will be: call=generate\_image, args:n=1,size=256x256, prompt:xxxx.
### **Image editing**
To edit an image, send a message to the bot with the image, an optional mask image, and a textual description of the desired changes. The bot will process the request and provide the edited image(s). The response format will be: call=edit\_image, args:n=1,size=256x256, prompt:xxxx.
### **Image variation**
To create variations of an image, send a message to the bot with the image and a request for variations. The bot will generate new images based on the original. The response format will be: call=create\_variation, args:n=1,size=256x256.
## **Limitations**
- The bot has a token limit of 2000 tokens for its message history, so longer conversations may result in some messages being removed from the history.
- The generated images may not always perfectly match the given descriptions.
- Image editing and variation capabilities depend on the quality and complexity of the input image and prompt.
## **Contributing**
We welcome contributions to improve the functionality and performance of the Slack Assistant Bot with Image Generation. Please feel free to submit a pull request or open an issue on the GitHub repository.
## **License**
This project is released under the [MIT License](https://opensource.org/licenses/MIT).
