import openai
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import requests
import logging
import datetime
from datetime import timedelta
import re
import giphy_client
from giphy_client.rest import ApiException
import gtts
import warnings
import redis
import json
from utils import *
from bs4 import BeautifulSoup
import ast
import operator as op

REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0


# Define las operaciones matemáticas permitidas
allowed_operators = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
                     ast.Div: op.truediv, ast.USub: op.neg}

def evaluate_expr(node):
    if isinstance(node, ast.Num):  # <number>
        return node.n
    elif isinstance(node, ast.BinOp):  # <left> <operator> <right>
        return allowed_operators[type(node.op)](evaluate_expr(node.left), evaluate_expr(node.right))
    elif isinstance(node, ast.UnaryOp):  # <operator> <operand> e.g., -1
        return allowed_operators[type(node.op)](evaluate_expr(node.operand))
    else:
        raise TypeError(node)

def calculate(expression):
    """Evaluate a math expression."""
    return evaluate_expr(ast.parse(expression, mode='eval').body)

class ImageGenerationComplete(Exception):
    pass

def save_all_message_histories_to_redis(message_histories):
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
    message_histories_str = {channel_id: json.dumps(history) for channel_id, history in message_histories.items()}
    r.hmset("message_histories", message_histories_str)

def load_all_message_histories_from_redis():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
    loaded_message_histories = r.hgetall("message_histories")
    if loaded_message_histories:
        return {channel_id.decode('utf-8'): json.loads(history) for channel_id, history in loaded_message_histories.items()}
    return {}

SLACK_APP_TOKEN = 'xapp-xxxxxxx'
SLACK_BOT_TOKEN = 'xoxb-yyyyyyy'

openai.api_key = "xxxxxxx"

# Configurar un registro personalizado
logging.basicConfig(level=logging.CRITICAL)
logger = logging.getLogger("slack_bolt")
logger.setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore", category=UserWarning, module="slack_sdk")

app = App(token=SLACK_BOT_TOKEN)

bot_user_id = None

GIPHY_API_KEY = "zzzzz"
giphy_api_instance = giphy_client.DefaultApi()

GOOGLE_API_KEY = "yyyyy"
GOOGLE_CSE_ID = "xxxx"

def search_web(query):
    """Search the web for a given query using Google Search API"""

    # Define la URL de la API y los parámetros de la búsqueda
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'q': query,
        'key': GOOGLE_API_KEY,
        'cx': GOOGLE_CSE_ID,
    }

    # Realiza la solicitud a la API
    response = requests.get(url, params=params)

    # Comprueba que la solicitud fue exitosa
    if response.status_code == 200:
        search_results = response.json()
        # Procesa los resultados de la búsqueda
        processed_results = []
        for result in search_results["items"][:2]:  # Limita a los primeros 3 resultados
            # Visita cada página de los resultados y extrae el texto
            page_response = requests.get(result["link"])
            if page_response.status_code == 200:
                soup = BeautifulSoup(page_response.content, "html.parser")
                # Elimina todos los scripts y estilos
                for script in soup(["script", "style"]):
                    script.extract()
                text = soup.get_text()
                # Rompe en líneas y elimina espacios en blanco al principio y al final
                lines = (line.strip() for line in text.splitlines())
                # Rompe líneas múltiples en una línea
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                # Elimina espacios en blanco
                text = '\n'.join(chunk for chunk in chunks if chunk)
                processed_results.append({
                    "title": result["title"],
                    "link": result["link"],
                    "content": text,
                })
        return json.dumps({"results": processed_results})
    else:
        return json.dumps({"error": "La búsqueda en la web falló"})

def get_url(url):
    """Fetch and summarize the content of a given URL"""

    # Fetch the content of the URL
    response = requests.get(url)

    # Check that the request was successful
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, "html.parser")
        # Remove all scripts and styles
        for script in soup(["script", "style"]):
            script.extract()
        text = soup.get_text()
        # Break into lines and remove leading and trailing space
        lines = (line.strip() for line in text.splitlines())
        # Break multi-headlines into a line
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # Drop blank lines
        text = '\n'.join(chunk for chunk in chunks if chunk)

        return text
    else:
        return json.dumps({"error": "Fetching the URL content failed"})

def search_gif(keyword):
    try:
        # Realiza una búsqueda en Giphy usando la palabra clave
        response = giphy_api_instance.gifs_search_get(GIPHY_API_KEY, keyword, limit=1, rating='g')

        if response.data:
            # Retorna la URL del primer GIF encontrado
            return response.data[0].images.fixed_height.url
        else:
            return None
    except ApiException as e:
        print(f"Error al buscar el GIF: {e}")
        return None

def generate_summary(text, file_type):

    # Configura el historial de mensajes con el asistente especializado en resumir y hacer esquemas
    message_history = [
        {"role": "system", "content": "Eres un asistente especialista en resumir y hacer esquemas del contenido de textos siempre atendiendo a lo interesante de acuerdo al tipo de contenido detectado: txt, csv, word, pdf, php, etc. Como máximo el resumen debe tener 10000 caracteres. Si es codigo fuente quedate con lo importante, si es csv o excel memoriza la estructura, etc. Intenta que el texto tenga como máximo 10000 caracteres y abarca toda la informacion que puedas sacar del mismo para el uso de este resumen en el futuro."},
        {"role": "user", "content": f"Por favor, resume este texto de tipo {file_type}: {text}"}
    ]

    # Llama a la API de ChatGPT de OpenAI
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo-16k",
        messages=message_history
    )

    # Obtiene el resumen del texto
    summary = response.choices[0].message.content

    # Limita el resumen a 10000 caracteres
    summary = ' '.join(summary.split()[:10000])

    return summary

def generate_image(channel_id, n=1, size = "1024x1024", prompt=""):
    # Llama a la API para generar la imagen
    image_response = openai.Image.create(
        prompt=prompt,
        n=n,
        size=size
    )

    image_urls = [data["url"] for data in image_response["data"]]

    # Construye bloques de imágenes para enviar al canal de Slack
    image_blocks = build_image_blocks(image_urls)

    # Envía las imágenes generadas al canal de slack
    app.client.chat_postMessage(
        channel=channel_id,
        text=f"Aquí tienes {n} imagen(es) generada(s)",
        blocks=image_blocks
    )

# Iniciar la aplicación
def start():
    global bot_user_id

    auth_response = app.client.auth_test(token=SLACK_BOT_TOKEN)
    bot_user_id = auth_response['user_id']
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()

# Evento de detección de nuevos mensajes
@app.event("message")
def command_handler(body, say):
    global message_histories, bot_user_id
    event = body['event']
    channel_id = body['event']['channel']
    channel_type = event.get('channel_type')
    user_id = event.get('user')
    files = event.get('files', [])

    if user_id == bot_user_id:
        return  # Ignorar mensajes del propio bot

    if channel_type in ('channel', 'im'):
        text = body['event']['text']

        if channel_id not in message_histories:
            message_histories[channel_id] = [{"role": "system", "content": "Eres un asistente trabajando en un canal de Slack. Usa por lo tanto emoticonos y formateo de textos adecuados a Slack. Vas a recordar que ha dicho cada usuario del canal porque su mensaje en tu conexto sera el de <@{user_id}>: su mensaje, por ejemplo <@U04V4HVBEAJ>: hola canal! Sin embargo tu respuesta como asistente no contendra este formato sino que simplemente responderas tu mensaje sin el <@{user_id}> (current_timestamp). La hora actual para ti como asistente será la hora registrada en el (current_timestamp) del último mensaje del historial de mensajes. Utiliza esa información para saber a qué día y hora estamos.Cuando vayas a referirte a un user_id concreto usa el formato <@user_id>."}]

        # Agregar el nombre del usuario y la fecha actual al mensaje antes de añadirlo al historial
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        madrid_offset = timedelta(hours=2)
        current_timestamp = (now_utc + madrid_offset).strftime("%Y-%m-%d %H:%M:%S")

        # Reemplazar el ID de usuario en el texto con su nombres de usuario
        username = get_username_from_id(app.client, user_id)

        if files:
            # Lee solo el primer archivo
            file = files[0]
            file_type = file["filetype"]

            if file_type not in ["jpg", "jpeg", "png", "gif"]:
                content = read_file(file, SLACK_BOT_TOKEN)
                if content:
                    # Llama a la API de ChatGPT para generar el resumen
                    resumen = generate_summary(content, file_type)
                    if resumen:
                        # Reemplazar el ID de usuario en el texto con su nombres de usuario
                        botusername = get_username_from_id(app.client, bot_user_id)

                        # Agrega el mensaje con el resumen al historial del canal
                        message_file = f"{botusername} ({current_timestamp}): el usuario {username} ha adjuntado un fichero de tipo {file_type} cuyo resumen o esquema es: {resumen}"

                        # Verificar si el nuevo mensaje excede el límite de tokens
                        while get_total_tokens(message_histories[channel_id]) + len(message_file) > 3500:
                             if len(message_histories[channel_id]) > 1:
                                 message_histories[channel_id] = [message_histories[channel_id][0]] + message_histories[channel_id][2:]
                             else:
                                 break  # Si solo hay un mensaje de "system" en el historial, interrumpir el bucle

                        message_histories[channel_id].append({"role": "assistant", "content": message_file})

        text = f"{username} ({current_timestamp}): {text}"

        text = remove_weird_chars(text).replace("(audio)", "")
    
        # Verificar si el nuevo mensaje excede el límite de tokens
        while get_total_tokens(message_histories[channel_id]) + len(text.split()) > 3500:
            if len(message_histories[channel_id]) > 1:
                message_histories[channel_id] = [message_histories[channel_id][0]] + message_histories[channel_id][2:]
            else:
               break  # Si solo hay un mensaje de "system" en el historial, interrumpir el bucle
        
        message_histories[channel_id].append({"role": "user", "content": text})

        # Comprobar si el bot ha sido mencionado
        if channel_type == 'im' or (channel_type == 'channel' and f'<@{bot_user_id}>' in body['event']['text']):
            try:
                # Define las funciones a las que el modelo tiene acceso
                functions = [
                    {
                        "name": "search_web",
                        "description": "Busca información en la web para una consulta dada",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "La consulta que quieres buscar en la web",
                                },
                            },
                            "required": ["query"],
                        },
                    },
                    {
                        "name": "generate_image",
                        "description": "Crea o genera imagenes a partir de un prompt dado",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "n": {
                                    "type": "integer",
                                    "description": "El número de imágenes a generar. Un número entero el 1 por defecto",
                                },
                                "size": {
                                    "type": "string",
                                    "description": "El tamaño de las imágenes a generar. Opciones: ['256x256', '512x512', '1024x1024']",
                                },
                                "prompt": {
                                    "type": "string",
                                    "description": "El prompt para generar las imágenes",
                                },
                            },
                            "required": ["n", "size", "prompt"],
                        },
                    },
                    {
                        "name": "search_gif",
                        "description": "Busca un GIF a partir de una palabra clave dada",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "keyword": {
                                    "type": "string",
                                    "description": "La palabra clave para buscar el GIF",
                                },
                            },
                            "required": ["keyword"],
                        },
                    },
                    {
                        "name": "get_url",
                        "description": "Accede al contenido específico de una página web dada en tiempo real y lo devuelve resuimido según las necesidades del contexto",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "url": {
                                    "type": "string",
                                    "description": "La URL de la web cuyo contenido quieres obtener",
                                },
                            },
                            "required": ["url"],
                        },
                    }, 
                    {
                        "name": "calculate",
                        "description": "Calcula una expresión matemática dada",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "expression": {
                                    "type": "string",
                                    "description": "La expresión a calcular (solo valen multiplicaciones, divisiones, restas y sumas)",
                                },
                            },
                            "required": ["expression"],
                        },
                    }
                ]

                # Llama al modelo con las funciones definidas
                response = openai.ChatCompletion.create(
                    model="gpt-3.5-turbo-16k-0613",
                    messages=message_histories[channel_id],
                    functions=functions,
                    function_call="auto",
                )

                message = response["choices"][0]["message"]
                reason = response["choices"][0]["finish_reason"]

                # Comprueba si el modelo quiere llamar a una función
                while reason == "function_call":                    
                    function_name = message["function_call"]["name"]
                    
                    # Carga la cadena JSON en un diccionario de Python
                    arguments = json.loads(message["function_call"]["arguments"])

                    if function_name == "search_web":
                        # Ahora puedes acceder al valor de "query"
                        query = arguments["query"]

                        # Llama a la función
                        function_response = search_web(
                            query=query,
                        )

                        # Limita la longitud de la respuesta a un máximo de 15000 caracteres
                        function_response = function_response[:15000]

                        # Llama al modelo de nuevo enviando la respuesta de la función como un nuevo mensaje
                        response = openai.ChatCompletion.create(
                            model="gpt-3.5-turbo-16k-0613",
                            messages=[
                                *message_histories[channel_id],
                                message,
                                {
                                    "role": "function",
                                    "name": function_name,
                                    "content": function_response,
                                }
                            ],
                            functions=functions,
                            function_call="auto"
                        )   

                        # Añade la respuesta de la función al historial de mensajes
                        message_histories[channel_id].append({
                            "role": "function",
                            "name": function_name,
                            "content": function_response,
                        })

                        message = response["choices"][0]["message"]
                        reason = response["choices"][0]["finish_reason"]

                    elif function_name == "get_url":
                        # Ahora puedes acceder al valor de "url"
                        url = arguments["url"]

                        # Llama a la función
                        function_response = get_url(
                            url=url,
                        )

                        # Limita la longitud de la respuesta a un máximo de 15000 caracteres
                        function_response = function_response[:15000]
                        
                        # Llama al modelo de nuevo enviando la respuesta de la función como un nuevo mensaje
                        response = openai.ChatCompletion.create(
                            model="gpt-3.5-turbo-16k-0613",
                            messages=[
                                *message_histories[channel_id],
                                message,
                                {
                                    "role": "function",
                                    "name": function_name,
                                    "content": function_response,
                                }
                            ],
                            functions=functions,
                            function_call="auto"
                        )

                        # Añade la respuesta de la función al historial de mensajes
                        message_histories[channel_id].append({
                            "role": "function",
                            "name": function_name,
                            "content": function_response,
                        })

                        message = response["choices"][0]["message"]
                        reason = response["choices"][0]["finish_reason"]

                    elif function_name == "calculate":
                        # Ahora puedes acceder al valor de "expression"
                        expression = arguments["expression"]

                        # Llama a la función
                        result = calculate(expression)

                        function_response = f"El resultado de la operación es {result}"

                        # Llama al modelo de nuevo enviando la respuesta de la función como un nuevo mensaje
                        response = openai.ChatCompletion.create(
                            model="gpt-3.5-turbo-16k-0613",
                            messages=[
                                *message_histories[channel_id],
                                message,
                                {
                                    "role": "function",
                                    "name": function_name,
                                    "content": function_response,
                                }
                            ],
                            functions=functions,
                            function_call="auto"
                        )

                        # Añade la respuesta de la función al historial de mensajes
                        message_histories[channel_id].append({
                            "role": "function",
                            "name": function_name,
                            "content": function_response,
                        })

                        message = response["choices"][0]["message"]
                        reason = response["choices"][0]["finish_reason"]

                    elif function_name == "generate_image":
                        # Ahora puedes acceder a los valores de "n", "size" y "prompt"
                        n = arguments["n"]
                        size = arguments["size"]
                        prompt = arguments["prompt"]

                        # Llama a la función
                        generate_image(
                            channel_id,
                            n=n,
                            size=size,
                            prompt=prompt
                        )

                        message_histories[channel_id].pop()

                        raise ImageGenerationComplete
                    
                    elif function_name == "search_gif":
                        # Ahora puedes acceder al valor de "keyword"
                        keyword = arguments["keyword"]

                        # Llama a la función
                        gif_url = search_gif(keyword)

                        if gif_url:
                            say(f"Aquí tienes un GIF sobre {keyword}: {gif_url}")
                        else:
                            say(f"No pude encontrar un GIF sobre {keyword}.")

                        message_histories[channel_id].pop()

                        raise ImageGenerationComplete
                    
                answer = message['content'].strip()
                answer = answer.replace("(current_timestamp):", "")
                answer = answer.replace("(current_timestamp)", str(current_timestamp))

                # Eliminar el formato de entrada al comienzo de la respuesta, si está presente
                answer = re.sub(r'^\w+\s\(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\): ', '', answer)

                # Reemplazar los IDs de usuario en el texto con sus nombres de usuario
                answer = replace_user_ids_with_usernames(app.client, answer)

                say(answer)

                try:
                    if "(audio)" in body['event']['text']:
                        tts = gtts.gTTS(answer, lang="es")
                        mp3_file = "response.mp3"
                        tts.save(mp3_file)
                        response = app.client.files_upload_v2(channels=channel_id,file=mp3_file,title="Respuesta en audio")
                except Exception as e:
                    say(f"Error al enviar el archivo MP3: {e}")

                # Reemplazar el ID de usuario en el texto con su nombres de usuario
                botusername = get_username_from_id(app.client, bot_user_id)

                # Agregar la fecha actual al mensaje del asistente
                answer = f"{botusername} ({current_timestamp}): {answer}"

                # Verificar si la respuesta del asistente excede el límite de tokens
                while get_total_tokens(message_histories[channel_id]) + len(answer.split()) > 3500:
                    if len(message_histories[channel_id]) > 1:
                        message_histories[channel_id] = [message_histories[channel_id][0]] + message_histories[channel_id][2:]
                    else:
                        break  # Si solo hay un mensaje de "system" en el historial, interrumpir el bucle

                message_histories[channel_id].append({"role": "assistant", "content": answer})
            except ImageGenerationComplete:
                pass
            except Exception as e:
                print(e)
                say("Lo siento, no puedo responder en este momento.")

                if len(message_histories[channel_id]) > 1:
                    message_histories[channel_id].pop(1)  # Eliminar el mensaje en la posición 1
                message_histories[channel_id].pop()  # Eliminar el último mensaje añadido            

        save_all_message_histories_to_redis(message_histories)

if __name__ == "__main__":
    message_histories = load_all_message_histories_from_redis()
    start()
