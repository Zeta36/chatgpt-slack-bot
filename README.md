# OpenAI GPT Slack Bot

This repository contains the source code for a Slack bot powered by OpenAI's GPT-3.5-turbo model. The bot is capable of responding to user messages in a conversational manner and can perform various tasks such as web search, image generation, GIF search, URL summarization, and basic arithmetic calculations.

## Features

- **Conversational AI**: The bot uses OpenAI's GPT-3.5-turbo model to generate human-like text based on the conversation history.
- **Web Search**: The bot can search the web for information using a custom function that interacts with the Google Search API.
- **Image Generation**: The bot can generate images based on a given prompt using OpenAI's Image API.
- **GIF Search**: The bot can search for GIFs based on a keyword using the Giphy API.
- **URL Summarization**: The bot can summarize the content of a given URL using a custom function that scrapes and processes the webpage content.
- **Basic Arithmetic Calculations**: The bot can perform basic arithmetic calculations (addition, subtraction, multiplication, and division) using a custom function.

## Installation

1. Clone this repository.
2. Install the required Python packages using pip: `pip install -r requirements.txt`
3. Set up your environment variables for the OpenAI API key, Google Search API key, Google CSE ID, and Giphy API key.
4. Run the bot: `python bot.py`

## Usage

Once the bot is running, you can interact with it in Slack. The bot can be mentioned in a channel or messaged directly. It will respond to user messages and perform tasks based on the content of the messages.

## Contributing

Contributions are welcome! Please feel free to submit a pull request.

## License

This project is licensed under the MIT License. See the LICENSE file for details.
