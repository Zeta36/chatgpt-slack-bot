import requests
import re
import pdfplumber
import PyPDF2
from docx import Document
import tempfile
import pandas as pd

def read_txt_file(url, token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    text = response.text
    return text[:15000]

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

    return text[:15000]

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

    return text[:15000]

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

    return text[:15000]

def read_csv_file(url, token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()

    text = response.text
    return text[:15000]

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

def remove_weird_chars(text):
    return re.sub(r"[^a-zA-Z0-9\s.,ñ:áéíóú?+<@>!¡¿()&€@#_\-/*\"':;%=\\`~%\[\]{}^$@;:'\"+#.,°<>]", "", text)

def get_total_tokens(messages):
    total_tokens = 0
    for message in messages:
        total_tokens += len(message["content"].split())
    return total_tokens

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