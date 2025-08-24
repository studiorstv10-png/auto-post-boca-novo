# ==============================================================================
# BLOCO 1: IMPORTAÇÕES E CONFIGURAÇÃO
# ==============================================================================
import os
import io
import requests
import textwrap
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from base64 import b64encode
import cloudinary
import cloudinary.uploader

load_dotenv()
app = Flask(__name__)

print("🚀 INICIANDO ARTISTA DE REELS v4.0 (FINAL)")

# --- Carregar e verificar variáveis ---
WP_URL = os.getenv('WP_URL')
WP_USER = os.getenv('WP_USER')
WP_PASSWORD = os.getenv('WP_PASSWORD')
META_API_TOKEN = os.getenv('USER_ACCESS_TOKEN')
INSTAGRAM_ID = os.getenv('INSTAGRAM_ID')
FACEBOOK_PAGE_ID = os.getenv('FACEBOOK_PAGE_ID')
CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME')
CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET')
MAKE_WEBHOOK_URL = os.getenv('MAKE_WEBHOOK_URL') # Nova variável!

# Configurar headers e Cloudinary
credentials = f"{WP_USER}:{WP_PASSWORD}"
token_wp = b64encode(credentials.encode())
HEADERS_WP = {'Authorization': f'Basic {token_wp.decode("utf-8")}'}
cloudinary.config(cloud_name=CLOUDINARY_CLOUD_NAME, api_key=CLOUDINARY_API_KEY, api_secret=CLOUDINARY_API_SECRET)

# ==============================================================================
# BLOCO 2: FUNÇÕES DE CRIAÇÃO E UPLOAD DE IMAGEM
# ==============================================================================
def criar_imagem_reel(url_imagem_noticia, titulo_post, categoria):
    print("🎨 [ETAPA 1/3] Criando imagem para o Reel...")
    try:
        response_img = requests.get(url_imagem_noticia, stream=True, timeout=15)
        response_img.raise_for_status()
        imagem_noticia = Image.open(io.BytesIO(response_img.content)).convert("RGBA")
        logo = Image.open("logo_boca.png").convert("RGBA")

        IMG_WIDTH, IMG_HEIGHT = 1080, 1920
        # ... (O resto do código de criação de imagem é idêntico e já funciona)
        cor_fundo = (0, 0, 0, 255)
        cor_vermelha = "#e50000"
        cor_branca = "#ffffff"
        fonte_categoria = ImageFont.truetype("Anton-Regular.ttf", 55)
        fonte_titulo = ImageFont.truetype("Roboto-Black.ttf", 72)
        imagem_final = Image.new('RGBA', (IMG_WIDTH, IMG_HEIGHT), cor_fundo)
        draw = ImageDraw.Draw(imagem_final)
        img_w, img_h = 1080, 960
        imagem_noticia_resized = imagem_noticia.resize((img_w, img_h), Image.Resampling.LANCZOS)
        imagem_final.paste(imagem_noticia_resized, (0, 0))
        logo.thumbnail((300, 300))
        pos_logo_x = (IMG_WIDTH - logo.width) // 2
        pos_logo_y = 960 - logo.height - 40
        imagem_final.paste(logo, (pos_logo_x, pos_logo_y), logo)
        y_cursor = 960 + 80
        draw.text((IMG_WIDTH / 2, y_cursor), categoria.upper(), font=fonte_categoria, fill=cor_vermelha, anchor="ma")
        y_cursor += 100
        linhas_texto = textwrap.wrap(titulo_post.upper(), width=25)
        texto_junto = "\n".join(linhas_texto)
        draw.text((IMG_WIDTH / 2, y_cursor + 20), texto_junto, font=fonte_titulo, fill=cor_branca, anchor="ma", align="center")

        buffer_saida = io.BytesIO()
        imagem_final.convert('RGB').save(buffer_saida, format='PNG')
        print("✅ [ETAPA 1/3] Imagem criada com sucesso!")
        return buffer_saida.getvalue()
    except Exception as e:
        print(f"❌ [ERRO] Falha na criação da imagem: {e}")
        return None

def upload_imagem_para_cloudinary(bytes_imagem):
    print("☁️ [ETAPA 2/3] Fazendo upload da IMAGEM para o Cloudinary...")
    try:
        resultado = cloudinary.uploader.upload(bytes_imagem, resource_type="image")
        url_segura = resultado.get('secure_url')
        if not url_segura: raise ValueError("Cloudinary não retornou uma URL.")
        print("✅ [ETAPA 2/3] Upload da imagem concluído!")
        return url_segura
    except Exception as e:
        print(f"❌ [ERRO Cloudinary] Falha no upload da imagem: {e}")
        return None

# ==============================================================================
# BLOCO 3: O MAESTRO (RECEPTOR DO WEBHOOK)
# ==============================================================================
@app.route('/webhook-boca', methods=['POST'])
def webhook_receiver():
    print("\n" + "="*50)
    print("🔔 [ARTISTA] Webhook recebido!")
    
    try:
        dados_brutos = request.json
        dados_wp = dados_brutos[0] if isinstance(dados_brutos, list) and dados_brutos else dados_brutos
        post_id = dados_wp.get('post_id')
        if not post_id: raise ValueError("Webhook não continha o 'post_id'.")

        print(f"🔍 [API WP] Buscando detalhes do post ID: {post_id}...")
        url_api_post = f"{WP_URL}/wp-json/wp/v2/posts/{post_id}"
        response_post = requests.get(url_api_post, headers=HEADERS_WP, timeout=15)
        response_post.raise_for_status()
        post_data = response_post.json()

        titulo_noticia = BeautifulSoup(post_data.get('title', {}).get('rendered', ''), 'html.parser').get_text()
        resumo_noticia = BeautifulSoup(post_data.get('excerpt', {}).get('rendered', ''), 'html.parser').get_text(strip=True)
        id_imagem_destaque = post_data.get('featured_media')

        categoria = "Notícias"
        # ... (lógica para buscar categoria)

        if not id_imagem_destaque: raise ValueError("Post não possui imagem de destaque.")
        
        url_api_media = f"{WP_URL}/wp-json/wp/v2/media/{id_imagem_destaque}"
        response_media = requests.get(url_api_media, headers=HEADERS_WP, timeout=15)
        url_imagem_destaque = response_media.json().get('source_url')
            
    except Exception as e:
        print(f"❌ [ERRO] Falha ao processar dados: {e}")
        return jsonify({"status": "erro_processamento_wp"}), 500

    imagem_bytes = criar_imagem_reel(url_imagem_destaque, titulo_noticia, categoria)
    if not imagem_bytes: return jsonify({"status": "erro_criacao_imagem"}), 500
    
    url_imagem_publica = upload_imagem_para_cloudinary(imagem_bytes)
    if not url_imagem_publica: return jsonify({"status": "erro_upload_cloudinary"}), 500

    # --- ETAPA FINAL: Chamar o Editor de Vídeo (Make.com) ---
    print("📢 [ETAPA 3/3] Acionando o Editor de Vídeo (Make.com)...")
    legenda_final = f"{titulo_noticia.upper()}\n\n{resumo_noticia}\n\nLeia a matéria completa!\n\n#noticias #{categoria.replace(' ', '').lower()} #litoralnorte"
    
    dados_para_make = {
        "imagem_url": url_imagem_publica,
        "legenda": legenda_final,
        "audio_url": "URL_DO_SEU_AUDIO_NO_CLOUDINARY" # Suba seu audio_fundo.mp3 para o Cloudinary e cole o link aqui
    }
    
    requests.post(MAKE_WEBHOOK_URL, json=dados_para_make)
    print("✅ [SUCESSO] Trabalho do Artista concluído!")
    return jsonify({"status": "sucesso_acionamento_make"}), 200

# ==============================================================================
# BLOCO 4: INICIALIZAÇÃO
# ==============================================================================
@app.route('/')
def health_check():
    return "Serviço Artista de Reels v4.0 está no ar.", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
