# ==============================================================================
# BLOCO 1: IMPORTAÇÕES E CONFIGURAÇÃO
# ==============================================================================
import os
import io
import requests
import textwrap
import subprocess
import tempfile
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from base64 import b64encode
import cloudinary
import cloudinary.uploader

load_dotenv()
app = Flask(__name__)

print("🚀 INICIANDO ARTISTA DE REELS v4.1 (Ajustes de Design)")

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
MAKE_WEBHOOK_URL = os.getenv('MAKE_WEBHOOK_URL')

# Configurar headers e Cloudinary
credentials = f"{WP_USER}:{WP_PASSWORD}"
token_wp = b64encode(credentials.encode())
HEADERS_WP = {'Authorization': f'Basic {token_wp.decode("utf-8")}'}
cloudinary.config(cloud_name=CLOUDINARY_CLOUD_NAME, api_key=CLOUDINARY_API_KEY, api_secret=CLOUDINARY_API_SECRET)

# ==============================================================================
# BLOCO 2: FUNÇÕES DE CRIAÇÃO E UPLOAD DE IMAGEM
# ==============================================================================
def criar_imagem_reel(url_imagem_noticia, titulo_post, categoria):
    print("🎨 [ETAPA 1/3] Criando imagem para o Reel com novo design...")
    try:
        response_img = requests.get(url_imagem_noticia, stream=True, timeout=15)
        response_img.raise_for_status()
        imagem_noticia = Image.open(io.BytesIO(response_img.content)).convert("RGBA")
        logo = Image.open("logo_boca.png").convert("RGBA")

        IMG_WIDTH, IMG_HEIGHT = 1080, 1920
        cor_fundo = (0, 0, 0, 255)
        cor_vermelha = "#e50000"
        cor_branca = "#ffffff"
        
        # --- AJUSTES DE DESIGN APLICADOS AQUI ---
        fonte_categoria = ImageFont.truetype("Anton-Regular.ttf", 70) # Fonte maior
        fonte_titulo = ImageFont.truetype("Roboto-Black.ttf", 72)

        imagem_final = Image.new('RGBA', (IMG_WIDTH, IMG_HEIGHT), cor_fundo)
        draw = ImageDraw.Draw(imagem_final)

        img_w, img_h = 1080, 960
        imagem_noticia_resized = imagem_noticia.resize((img_w, img_h), Image.Resampling.LANCZOS)
        imagem_final.paste(imagem_noticia_resized, (0, 0))

        # Logo posicionado no início da área preta
        logo.thumbnail((300, 300))
        pos_logo_x = (IMG_WIDTH - logo.width) // 2
        pos_logo_y = 960 - (logo.height // 2) # Centralizado na linha divisória
        imagem_final.paste(logo, (pos_logo_x, pos_logo_y), logo)

        y_cursor = 960 + (logo.height // 2) + 60 # Posição inicial abaixo do logo

        # Categoria (faixa vermelha com texto branco)
        texto_categoria = categoria.upper()
        cat_bbox = draw.textbbox((0, 0), texto_categoria, font=fonte_categoria)
        text_width = cat_bbox[2] - cat_bbox[0]
        text_height = cat_bbox[3] - cat_bbox[1]
        
        banner_padding_x = 40
        banner_padding_y = 20
        banner_width = text_width + (banner_padding_x * 2)
        banner_height = text_height + (banner_padding_y * 2)
        
        banner_x0 = (IMG_WIDTH - banner_width) // 2
        banner_y0 = y_cursor
        
        draw.rectangle(
            [banner_x0, banner_y0, banner_x0 + banner_width, banner_y0 + banner_height],
            fill=cor_vermelha
        )
        
        draw.text(
            (IMG_WIDTH / 2, banner_y0 + (banner_height / 2)),
            texto_categoria,
            font=fonte_categoria,
            fill=cor_branca,
            anchor="mm"
        )
        y_cursor += banner_height + 40

        # Título
        linhas_texto = textwrap.wrap(titulo_post.upper(), width=25)
        texto_junto = "\n".join(linhas_texto)
        draw.text(
            (IMG_WIDTH / 2, y_cursor),
            texto_junto,
            font=fonte_titulo,
            fill=cor_branca,
            anchor="ma",
            align="center"
        )

        buffer_saida = io.BytesIO()
        imagem_final.convert('RGB').save(buffer_saida, format='PNG')
        print("✅ [ETAPA 1/3] Imagem com novo design criada com sucesso!")
        return buffer_saida.getvalue()
    except Exception as e:
        print(f"❌ [ERRO] Falha na criação da imagem: {e}")
        return None

# (O resto do código permanece exatamente o mesmo)
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
        try:
            if 'categories' in post_data and post_data['categories']:
                id_categoria = post_data['categories'][0]
                url_api_cat = f"{WP_URL}/wp-json/wp/v2/categories/{id_categoria}"
                response_cat = requests.get(url_api_cat, headers=HEADERS_WP, timeout=15)
                categoria = response_cat.json().get('name', 'Notícias')
        except Exception:
            print("  - Aviso: Não foi possível buscar a categoria.")

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

    print("📢 [ETAPA 3/3] Acionando o Editor de Vídeo (Make.com)...")
    legenda_final = f"{titulo_noticia.upper()}\n\n{resumo_noticia}\n\nLeia a matéria completa!\n\n#noticias #{categoria.replace(' ', '').lower()} #litoralnorte"
    
    dados_para_make = {
        "imagem_url": url_imagem_publica,
        "legenda": legenda_final,
        "audio_public_id": "audio_fundo" # Enviando o Public ID do áudio
    }
    
    requests.post(MAKE_WEBHOOK_URL, json=dados_para_make)
    print("✅ [SUCESSO] Trabalho do Artista concluído!")
    return jsonify({"status": "sucesso_acionamento_make"}), 200

@app.route('/')
def health_check():
    return "Serviço Artista de Reels v4.1 está no ar.", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
