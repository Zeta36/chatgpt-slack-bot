import openai
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import requests
import logging
import datetime
from datetime import timedelta
import re
import os
from urllib.request import urlretrieve
import giphy_client
from giphy_client.rest import ApiException
import pdfplumber
import PyPDF2
from docx import Document
import tempfile
from openpyxl import load_workbook
import pandas as pd
import gtts
import warnings

SLACK_APP_TOKEN = 'xapp-1-xxxx'
SLACK_BOT_TOKEN = 'xoxb-yyyyyy'

openai.api_key = "sk-zzzzzzzzz"

# Configurar un registro personalizado
logging.basicConfig(level=logging.CRITICAL)
logger = logging.getLogger("slack_bolt")
logger.setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore", category=UserWarning, module="slack_sdk")

app = App(token=SLACK_BOT_TOKEN)

bot_user_id = None

GIPHY_API_KEY = "XbkzGLFUruSsh2FUrMBVt4gUeHBIOgCF"
giphy_api_instance = giphy_client.DefaultApi()

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

def read_txt_file(url, token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    text = response.text
    return text[:6000]

def read_excel_file(url, token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    with tempfile.NamedTemporaryFile() as tmp_file:
        tmp_file.write(response.content)
        tmp_file.flush()

        df = pd.read_excel(tmp_file.name, engine='openpyxl')

    # Convert the DataFrame to a string
    text = df.to_string(index=False)

    return text[:6000]

def read_pdf_file(url, token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, stream=True)
    response.raise_for_status()

    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        tmp_file.write(response.content)
        tmp_file.flush()
        tmp_file_path = tmp_file.name

    text = ""
    with pdfplumber.open(tmp_file_path) as pdf:
        for page_num in range(min(len(pdf.pages), 3)):
            page = pdf.pages[page_num]
            extracted_text = page.extract_text()
            if not extracted_text:
                with open(tmp_file_path, "rb") as f:
                    pdf_reader = PyPDF2.PdfFileReader(f)
                    extracted_text = pdf_reader.getPage(page_num).extract_text()
            text += extracted_text

    return text[:6000]

def read_docx_file(url, token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, stream=True)
    response.raise_for_status()

    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        tmp_file.write(response.content)
        tmp_file.flush()
        tmp_file_path = tmp_file.name

    with open(tmp_file_path, "rb") as f:
        doc = Document(f)
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])

    return text[:6000]

def read_csv_file(url, token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    text = response.text
    return text[:6000]

def read_file(file, token):
    url = file['url_private']
    file_type = file['filetype']

    if file_type == "txt":
        content = read_txt_file(url, token)
    elif file_type == "pdf":
        content = read_pdf_file(url, token)
    elif file_type == "docx" or file_type == "doc":
        content = read_docx_file(url, token)
    elif file_type == "csv":
        content = read_csv_file(url, token)
    elif file_type == "xls" or file_type == "xlsx":
        content = read_excel_file(url, token)
    else:
        content = read_txt_file(url, token)

    return content

def generate_summary(text, file_type):

    # Configura el historial de mensajes con el asistente especializado en resumir y hacer esquemas
    message_history = [
        {"role": "system", "content": "Eres un asistente especialista en resumir y hacer esquemas del contenido de textos siempre atendiendo a lo interesante de acuerdo al tipo de contenido detectado: txt, csv, word, pdf, php, etc. Como máximo el resumen debe tener 1000 palabras. Si es codigo fuente quedate con lo importante, si es csv o excel memoriza la estructura, etc. Intenta que el texto tenga un contenido de sobre 2000 palabras y abarca toda la informacion que puedas sacar del mismo para el uso de este resumen en el futuro."},
        {"role": "user", "content": f"Por favor, resume este texto de tipo {file_type}: {text}"}
    ]

    # Llama a la API de ChatGPT de OpenAI
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=message_history
    )

    # Obtiene el resumen del texto
    summary = response.choices[0].message.content

    # Limita el resumen a 2000 palabras
    summary = ' '.join(summary.split()[:2000])

    return summary

def remove_weird_chars(text):
    return re.sub(r"[^a-zA-Z0-9\s.,ñ:áéíóú?+<@>!¡¿()&€@#_\-/*\"':;%=\\`~%\[\]{}^$@;:'\"+#.,°<>]", "", text)

def get_total_tokens(messages):
    total_tokens = 0
    for message in messages:
        total_tokens += len(message["content"].split())
    return total_tokens

# Iniciar la aplicación
def start():
    global bot_user_id

    auth_response = app.client.auth_test(token=SLACK_BOT_TOKEN)
    bot_user_id = auth_response['user_id']
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()


def get_username_from_id(slack_client, user_id):
    response = slack_client.users_info(user=user_id)
    if response['ok']:
        user_profile = response['user']
        return user_profile.get('real_name', 'name')
    else:
        return None


def replace_user_ids_with_usernames(slack_client, text):
    user_ids = re.findall(r'<@([A-Z0-9]+)>', text)

    for user_id in user_ids:
        username = get_username_from_id(slack_client, user_id)
        if username:
            text = text.replace(f'<@{user_id}>', f'*{username}*')
    return text

def image_request_system_message():
    return {
        "role": "system",
        "content": (
            "Eres un asistente que tiene la tarea de detectar si se solicita una imagen en un mensaje de texto. "
            "Si se solicita una imagen, primero debes mejorar y traducir el prompt al inglés eliminando "
            "cualquier referencia a 'size' o 'n' y asegurándote de que no haya preguntas ni peticiones al usuario. "
            "Luego, devuelve una respuesta en el formato 'call=generate_image, args:n=1,size=256x256, prompt:xxxx', "
            "donde 'xxxx' es el prompt mejorado y traducido al inglés. Si se solicita una edición de una imagen, "
            "devuelve 'call=edit_image, args:n=1,size=256x256, prompt:xxxx'. Si se solicita una variación de una imagen, "
            "devuelve 'call=create_variation, args:n=1,size=256x256'. Si se solicita un GIF animado, devuelve una respuesta en el formato 'call=generate_gif, args:prompt:xxxx', "
            "donde 'xxxx' es el keyword para buscar intenta resumir lo que se necesita sin mencionar la palabra gif se conciso. En cualquier otro caso devuelve 'call=None'. "
            "Devuelve exclusivamente con el formato tal cual sin ningun otro texto anterior o posterior al mismo."
        )
    }

def download_image(url, local_file_path, token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers, stream=True)
    response.raise_for_status()
    with open(local_file_path, "wb") as local_file:
        for chunk in response.iter_content(chunk_size=8192):
            local_file.write(chunk)

def build_image_blocks(image_urls):
    blocks = []
    for url in image_urls:
        block = {
            "type": "image",
            "image_url": url,
            "alt_text": "Imagen generada"
        }
        blocks.append(block)
    return blocks

# Evento de detección de nuevos mensajes
@app.event("message")
def command_handler(body, say):
    global message_histories, bot_user_id
    event = body['event']
    channel_id = body['event']['channel']
    channel_type = event.get('channel_type')
    user_id = event.get('user')
    files = event.get('files', [])
    images = [file for file in files if file.get('mimetype', '').startswith('image/')]

    image_url = None
    mask_url = None

    # Suponiendo que la primera imagen es la imagen principal y la segunda imagen es la máscara
    if len(images) >= 1:
        image_url = images[0]['url_private_download']
    if len(images) >= 2:
        mask_url = images[1]['url_private_download']

    if user_id == bot_user_id:
        return  # Ignorar mensajes del propio bot

    if channel_type in ('channel', 'im'):
        text = body['event']['text']

        if channel_id not in message_histories:
            message_histories[channel_id] = [{"role": "system", "content": "Eres un asistente trabajando en un canal de Slack. Usa por lo tanto emoticonos y formateo de textos adecuados a Slack. Vas a recordar que ha dicho cada usuario del canal porque su mensaje en tu conexto sera el de <@{user_id}>: su mensaje, por ejemplo <@U04V4HVBEAJ>: hola canal! Sin embargo tu respuesta como asistente no contendra este formato sino que simplemente responderas tu mensaje sin el <@{user_id}> (current_timestamp). La hora actual para ti como asistente será la hora registrada en el (current_timestamp) del último mensaje del historial de mensajes. Utiliza esa información para saber a qué día y hora estamos.Cuando vayas a referirte a un user_id concreto usa el formato <@user_id>"}]

        # Agregar el nombre del usuario y la fecha actual al mensaje antes de añadirlo al historial
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        madrid_offset = timedelta(hours=2)
        current_timestamp = (now_utc + madrid_offset).strftime("%Y-%m-%d %H:%M:%S")

        # Reemplazar el ID de usuario en el texto con su nombres de usuario
        username = get_username_from_id(app.client, user_id)

        has_summary = False
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
                        while get_total_tokens(message_histories[channel_id]) + len(message_file) > 6000:
                             if len(message_histories[channel_id]) > 1:
                                 message_histories[channel_id] = [message_histories[channel_id][0]] + message_histories[channel_id][2:]
                             else:
                                 break  # Si solo hay un mensaje de "system" en el historial, interrumpir el bucle

                        message_histories[channel_id].append({"role": "assistant", "content": message_file})
                        has_summary = True

        text = f"{username} ({current_timestamp}): {text}"

        text = remove_weird_chars(text)

        # Verificar si el nuevo mensaje excede el límite de tokens
        while get_total_tokens(message_histories[channel_id]) + len(text.split()) > 6000:
            if len(message_histories[channel_id]) > 1:
                message_histories[channel_id] = [message_histories[channel_id][0]] + message_histories[channel_id][2:]
            else:
               break  # Si solo hay un mensaje de "system" en el historial, interrumpir el bucle


        message_histories[channel_id].append({"role": "user", "content": text})

        # Comprobar si el bot ha sido mencionado
        if channel_type == 'im' or (channel_type == 'channel' and f'<@{bot_user_id}>' in body['event']['text']):

          # Determina si se solicita la generación de una imagen
          image_request_history = [image_request_system_message(), {"role": "user", "content": text}]

          try:
              response = openai.ChatCompletion.create(
                  model="gpt-3.5-turbo",
                  messages=image_request_history
              )

              image_request_answer = response.choices[0].message['content'].strip()

              # Procesa la respuesta del modelo para determinar si se solicita la generación de una imagen y extraer los parámetros
              call_match = re.search(r"call=(\w+)", image_request_answer)
              if call_match and call_match.group(1) == "generate_gif" and not has_summary:
                  match_prompt = re.search(r"prompt:(.*)", image_request_answer)
                  if match_prompt:
                      translated_prompt = match_prompt.group(1)
                  else:
                      translated_prompt = text

                  gif_url = search_gif(translated_prompt)

                  if gif_url:
                      say(f"Aquí tienes un GIF sobre {translated_prompt}: {gif_url}")
                  else:
                      say(f"No pude encontrar un GIF sobre {translated_prompt}.")

                  message_histories[channel_id].pop()

              elif call_match and call_match.group(1) == "generate_image" and not has_summary:
                  n = 1
                  size = "1024x1024"
                  match_n = re.search(r"n=(\d+)", image_request_answer)
                  match_size = re.search(r"size=(\d+x\d+)", image_request_answer)
                  match_prompt = re.search(r"prompt:(.*)", image_request_answer)
                  if match_prompt:
                    translated_prompt = match_prompt.group(1)
                  else:
                    translated_prompt = text
                  if match_n:
                      n = int(match_n.group(1))
                  if match_size:
                      size = match_size.group(1)

                  # Llama a la API para generar la imagen
                  image_response = openai.Image.create(
                      prompt=translated_prompt,
                      n=n,
                      size=size
                  )

                  image_urls = [data["url"] for data in image_response["data"]]

                  # Construye bloques de imágenes para enviar al canal de Slack
                  image_blocks = build_image_blocks(image_urls)

                  # Envía las imágenes generadas al canal
                  app.client.chat_postMessage(
                      channel=channel_id,
                      text=f"Aquí tienes {n} imagen(es) generada(s) a partir de la descripción: {text}",
                      blocks=image_blocks
                  )

                  message_histories[channel_id].pop()

              elif call_match and call_match.group(1) == "edit_image" and image_url and mask_url and not has_summary:
                n = 1
                size = "1024x1024"
                match_n = re.search(r"n=(\d+)", image_request_answer)
                match_size = re.search(r"size=(\d+x\d+)", image_request_answer)
                match_prompt = re.search(r"prompt:(.*)", image_request_answer)
                if match_prompt:
                  translated_prompt = match_prompt.group(1)
                else:
                  translated_prompt = text
                if match_n:
                    n = int(match_n.group(1))
                if match_size:
                    size = match_size.group(1)

                # Descargar las imágenes
                download_image(image_url, 'image.png', SLACK_BOT_TOKEN)
                download_image(mask_url, 'mask.png', SLACK_BOT_TOKEN)

                # Llamar a la API para editar la imagen
                image_response = openai.Image.create_edit(
                    image=open('image.png', "rb"),
                    mask=open('mask.png', "rb"),
                    prompt=translated_prompt,
                    n=n,
                    size=size
                )

                image_urls = [data["url"] for data in image_response["data"]]

                # Construye bloques de imágenes para enviar al canal de Slack
                image_blocks = build_image_blocks(image_urls)

                # Envía las imágenes generadas al canal
                app.client.chat_postMessage(
                    channel=channel_id,
                    text=f"Aquí tienes {n} imagen(es) generada(s) a partir de la descripción: {text}",
                    blocks=image_blocks
                )

                message_histories[channel_id].pop()

              elif call_match and call_match.group(1) == "create_variation" and image_url and not has_summary:
                n = 1
                size = "1024x1024"
                match_n = re.search(r"n=(\d+)", image_request_answer)
                match_size = re.search(r"size=(\d+x\d+)", image_request_answer)
                if match_n:
                    n = int(match_n.group(1))
                if match_size:
                    size = match_size.group(1)

                # Descargar las imágenes
                download_image(image_url, 'image.png', SLACK_BOT_TOKEN)

                # Llama a la API para generar variaciones de la imagen
                image_response = openai.Image.create_variation(
                    image=open('image.png', "rb"),
                    n=n,
                    size=size
                )

                image_urls = [data["url"] for data in image_response["data"]]

                # Construye bloques de imágenes para enviar al canal de Slack
                image_blocks = build_image_blocks(image_urls)

                # Envía las imágenes generadas al canal
                app.client.chat_postMessage(
                    channel=channel_id,
                    text=f"Aquí tienes {n} imagen(es) generada(s) a partir de la descripción: {text}",
                    blocks=image_blocks
                )

                message_histories[channel_id].pop()

              else:
                  try:
                    response = openai.ChatCompletion.create(
                        model="gpt-4",
                        messages=message_histories[channel_id]
                    )

                    answer = response.choices[0].message['content'].strip()
                    answer = answer.replace("(current_timestamp):", "")
                    answer = answer.replace("(current_timestamp)", str(current_timestamp))

                    # Eliminar el formato de entrada al comienzo de la respuesta, si está presente
                    answer = re.sub(r'^\w+\s\(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\): ', '', answer)

                    # Reemplazar los IDs de usuario en el texto con sus nombres de usuario
                    answer = replace_user_ids_with_usernames(app.client, answer)

                    say(answer)

                    try:
                        if len(answer) > 600 and len(answer) < 2000:
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

                  except Exception as e:
                    print(e)
                    say("Lo siento, no puedo responder en este momento.")

                    if len(message_histories[channel_id]) > 1:
                        message_histories[channel_id].pop(1)  # Eliminar el mensaje en la posición 1
                    message_histories[channel_id].pop()  # Eliminar el último mensaje añadido

                  # Verificar si la respuesta del asistente excede el límite de tokens
                  while get_total_tokens(message_histories[channel_id]) + len(answer.split()) > 6000:
                      if len(message_histories[channel_id]) > 1:
                          message_histories[channel_id] = [message_histories[channel_id][0]] + message_histories[channel_id][2:]
                      else:
                          break  # Si solo hay un mensaje de "system" en el historial, interrumpir el bucle

                  message_histories[channel_id].append({"role": "assistant", "content": answer})
          except Exception as e:
              print(e)
              say("Lo siento, no puedo generar una imagen en este momento.")

if __name__ == "__main__":
    message_histories = {}
    start()
