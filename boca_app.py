# ==============================================================================
# BLOCO 1: IMPORTAÇÕES
# ==============================================================================
import os
import io
import json
import requests
import textwrap
import subprocess
import tempfile
import time
import traceback
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from base64 import b64encode
import cloudinary
import cloudinary.uploader

# ==============================================================================
# BLOCO 2: CONFIGURAÇÃO INICIAL E VERIFICAÇÃO
# ==============================================================================
load_dotenv()
app = Flask(__name__)

print("🚀 INICIANDO AUTOMAÇÃO DE REELS v3.0 (VERSÃO DEFINITIVA)")

# --- VERIFICAÇÃO RIGOROSA DAS VARIÁVEIS DE AMBIENTE ---
required_vars = [
    'WP_URL', 'WP_USER', 'WP_PASSWORD', 'PAGE_TOKEN_BOCA', 'INSTAGRAM_ID',
    'FACEBOOK_PAGE_ID', 'CLOUDINARY_CLOUD_NAME', 'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET'
]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    error_message = f"❌ ERRO CRÍTICO: As seguintes variáveis de ambiente estão faltando: {', '.join(missing_vars)}. A aplicação não pode iniciar."
    print(error_message)
    # Em um ambiente real, isso deveria parar a aplicação.
    # Em Flask, a verificação ocorrerá em cada request.
else:
    print("✅ [CONFIG] Todas as variáveis de ambiente foram carregadas com sucesso.")

# Carregar variáveis após a verificação
WP_URL = os.getenv('WP_URL')
WP_USER = os.getenv('WP_USER')
WP_PASSWORD = os.getenv('WP_PASSWORD')
META_API_TOKEN = os.getenv('PAGE_TOKEN_BOCA')
INSTAGRAM_ID = os.getenv('INSTAGRAM_ID')
FACEBOOK_PAGE_ID = os.getenv('FACEBOOK_PAGE_ID')
CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME')
CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET')

# Configurar headers do WordPress
credentials = f"{WP_USER}:{WP_PASSWORD}"
token_wp = b64encode(credentials.encode())
HEADERS_WP = {'Authorization': f'Basic {token_wp.decode("utf-8")}'}

# Configurar Cloudinary
cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET
)

# ==============================================================================
# BLOCO 3: FUNÇÕES DE CRIAÇÃO DE MÍDIA
# ==============================================================================
def criar_imagem_reel(url_imagem_noticia, titulo_post, categoria):
    print("🎨 [ETAPA 1/5] Iniciando criação da imagem para o Reel...")
    try:
        response_img = requests.get(url_imagem_noticia, stream=True, timeout=15)
        response_img.raise_for_status()
        imagem_noticia = Image.open(io.BytesIO(response_img.content)).convert("RGBA")

        logo = Image.open("logo_boca.png").convert("RGBA")

        IMG_WIDTH, IMG_HEIGHT = 1080, 1920
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
        print("✅ [ETAPA 1/5] Imagem para o Reel criada com sucesso!")
        return buffer_saida.getvalue()

    except Exception as e:
        print(f"❌ [ERRO] Falha crítica na criação da imagem: {e}")
        return None

def criar_video_com_ffmpeg(bytes_imagem):
    print("🎥 [ETAPA 2/5] Criando vídeo com FFmpeg (SEM ÁUDIO)...")
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_image:
            tmp_image.write(bytes_imagem)
            tmp_image_path = tmp_image.name

        tmp_video_path = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4').name
        
        comando = [
            'ffmpeg', '-loop', '1', '-i', tmp_image_path,
            '-c:v', 'libx264', '-t', '10', '-pix_fmt', 'yuv420p',
            '-vf', 'scale=1080:1920', '-y', tmp_video_path
        ]
        
        subprocess.run(comando, check=True, capture_output=True, text=True)
        
        print(f"✅ [ETAPA 2/5] Vídeo (sem som) criado com sucesso em: {tmp_video_path}")
        return tmp_video_path

    except subprocess.CalledProcessError as e:
        print(f"❌ [ERRO FFmpeg] Falha ao criar vídeo: {e.stderr}")
        return None
    except Exception as e:
        print(f"❌ [ERRO GERAL] Falha na criação do vídeo: {e}")
        return None

def upload_para_cloudinary(caminho_video):
    print("☁️ [ETAPA 3/5] Fazendo upload do vídeo para o Cloudinary...")
    try:
        resultado = cloudinary.uploader.upload(
            caminho_video,
            resource_type="video",
            public_id=f"reel_{os.path.basename(caminho_video)}"
        )
        url_segura = resultado.get('secure_url')
        if not url_segura:
            raise ValueError("Cloudinary não retornou uma URL segura.")
        
        print("✅ [ETAPA 3/5] Upload para Cloudinary concluído!")
        return url_segura
    except Exception as e:
        print(f"❌ [ERRO Cloudinary] Falha no upload: {e}")
        return None

# ==============================================================================
# BLOCO 4: FUNÇÕES DE PUBLICAÇÃO
# ==============================================================================
def publicar_reel_no_instagram(video_url, legenda):
    print("📤 [ETAPA 4/5] Publicando Reel no Instagram...")
    try:
        url_container = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ID}/media"
        params_container = {
            'media_type': 'REELS', 'video_url': video_url,
            'caption': legenda, 'access_token': META_API_TOKEN
        }
        r_container = requests.post(url_container, params=params_container, timeout=30)
        r_container.raise_for_status()
        id_criacao = r_container.json()['id']
        print(f"  - Contêiner de mídia criado: {id_criacao}")

        url_publicacao = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ID}/media_publish"
        params_publicacao = {'creation_id': id_criacao, 'access_token': META_API_TOKEN}
        
        for i in range(10):
            print(f"  - Verificando status do upload (tentativa {i+1}/10)...")
            r_publish = requests.post(url_publicacao, params=params_publicacao, timeout=30)
            if r_publish.status_code == 200:
                print("✅ [ETAPA 4/5] Reel publicado no Instagram com sucesso!")
                return True
            
            error_info = r_publish.json().get('error', {})
            if error_info.get('code') == 9007:
                print("  - Vídeo ainda processando, aguardando 10 segundos...")
                time.sleep(10)
            else:
                raise requests.exceptions.HTTPError(response=r_publish)

        print("❌ [ERRO INSTAGRAM] Tempo de processamento do vídeo esgotado.")
        return False

    except requests.exceptions.HTTPError as e:
        print(f"❌ [ERRO HTTP INSTAGRAM] Falha ao publicar: {e.response.text}")
        return False
    except Exception as e:
        print(f"❌ [ERRO GERAL INSTAGRAM] Falha: {e}")
        return False

def publicar_reel_no_facebook(video_url, legenda):
    print("📤 [ETAPA 5/5] Publicando Reel no Facebook...")
    try:
        url_post_video = f"https://graph.facebook.com/v19.0/{FACEBOOK_PAGE_ID}/videos"
        params = {
            'file_url': video_url, 'description': legenda, 
            'access_token': META_API_TOKEN
        }
        r = requests.post(url_post_video, params=params, timeout=180)
        r.raise_for_status()
        print("✅ [ETAPA 5/5] Reel publicado no Facebook com sucesso!")
        return True
    except requests.exceptions.HTTPError as e:
        print(f"❌ [ERRO HTTP FACEBOOK] Falha ao publicar: {e.response.text}")
        return False
    except Exception as e:
        print(f"❌ [ERRO GERAL FACEBOOK] Falha: {e}")
        return False

# ==============================================================================
# BLOCO 5: O MAESTRO (RECEPTOR DO WEBHOOK)
# ==============================================================================
@app.route('/webhook-boca', methods=['POST'])
def webhook_receiver():
    print("\n" + "="*50)
    print("🔔 [WEBHOOK] Webhook para REEL recebido!")
    
    # --- VERIFICAÇÃO DE VARIÁVEIS EM CADA REQUEST ---
    if missing_vars:
        return jsonify({"status": "erro_configuracao", "message": f"Faltando variáveis: {', '.join(missing_vars)}"}), 500

    try:
        # --- LÓGICA ROBUSTA PARA PARSE DO WEBHOOK ---
        dados_brutos = request.json
        if isinstance(dados_brutos, list) and dados_brutos:
            dados_wp = dados_brutos[0]
        else:
            dados_wp = dados_brutos
        
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

        if id_imagem_destaque and id_imagem_destaque > 0:
            url_api_media = f"{WP_URL}/wp-json/wp/v2/media/{id_imagem_destaque}"
            response_media = requests.get(url_api_media, headers=HEADERS_WP, timeout=15)
            response_media.raise_for_status()
            url_imagem_destaque = response_media.json().get('source_url')
        else:
            raise ValueError("Post não possui imagem de destaque, não é possível criar Reel.")
            
    except Exception as e:
        print(f"❌ [ERRO CRÍTICO] Falha ao processar dados do webhook ou buscar no WordPress: {e}")
        return jsonify({"status": "erro_processamento_wp", "message": str(e)}), 500

    print("\n🚀 INICIANDO FLUXO DE CRIAÇÃO E PUBLICAÇÃO...")
    
    imagem_bytes = criar_imagem_reel(url_imagem_destaque, titulo_noticia, categoria)
    if not imagem_bytes: return jsonify({"status": "erro_criacao_imagem"}), 500
    
    caminho_video = criar_video_com_ffmpeg(imagem_bytes)
    if not caminho_video: return jsonify({"status": "erro_criacao_video"}), 500

    url_video_publica = upload_para_cloudinary(caminho_video)
    if not url_video_publica: return jsonify({"status": "erro_upload_cloudinary"}), 500

    legenda_final = f"{titulo_noticia.upper()}\n\n{resumo_noticia}\n\nLeia a matéria completa!\n\n#noticias #{categoria.replace(' ', '').lower()} #litoralnorte"
    
    sucesso_ig = publicar_reel_no_instagram(url_video_publica, legenda_final)
    sucesso_fb = publicar_reel_no_facebook(url_video_publica, legenda_final)

    if sucesso_ig or sucesso_fb:
        print("🎉 [SUCESSO] Automação concluída!")
        return jsonify({"status": "sucesso_publicacao"}), 200
    else:
        print("😭 [FALHA] Nenhuma publicação foi bem-sucedida.")
        return jsonify({"status": "erro_publicacao_redes"}), 500

# ==============================================================================
# BLOCO 6: INICIALIZAÇÃO
# ==============================================================================
@app.route('/')
def health_check():
    return "Serviço de automação de REELS v3.0 está no ar.", 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
