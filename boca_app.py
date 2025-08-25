# ==============================================================================
# BLOCO 1: IMPORTAÇÕES E CONFIGURAÇÃO
# ==============================================================================
import os
import io
import requests
import textwrap
import time
from flask import Flask, request, jsonify
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from base64 import b64encode
import cloudinary
import cloudinary.uploader
import cloudinary.api

load_dotenv()
app = Flask(__name__)

print("🚀 INICIANDO AUTOMAÇÃO DE REELS v16.0 (SOLUÇÃO DEFINITIVA FINAL)")

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

# Configurar headers e Cloudinary
credentials = f"{WP_USER}:{WP_PASSWORD}"
token_wp = b64encode(credentials.encode())
HEADERS_WP = {'Authorization': f'Basic {token_wp.decode("utf-8")}'}
cloudinary.config(cloud_name=CLOUDINARY_CLOUD_NAME, api_key=CLOUDINARY_API_KEY, api_secret=CLOUDINARY_API_SECRET)

# ==============================================================================
# BLOCO 2: FUNÇÕES DE MÍDIA
# ==============================================================================
def criar_imagem_reel(url_imagem_noticia, titulo_post, categoria):
    print("🎨 [ETAPA 1/4] Criando imagem base para o Reel...")
    try:
        response_img = requests.get(url_imagem_noticia, stream=True, timeout=15)
        response_img.raise_for_status()
        imagem_noticia = Image.open(io.BytesIO(response_img.content)).convert("RGBA")
        logo = Image.open("logo_boca.png").convert("RGBA")

        IMG_WIDTH, IMG_HEIGHT = 1080, 1920
        cor_fundo = (0, 0, 0, 255)
        cor_vermelha = "#e50000"
        cor_branca = "#ffffff"
        fonte_categoria = ImageFont.truetype("Anton-Regular.ttf", 70)
        fonte_titulo = ImageFont.truetype("Roboto-Black.ttf", 72)

        imagem_final = Image.new('RGBA', (IMG_WIDTH, IMG_HEIGHT), cor_fundo)
        draw = ImageDraw.Draw(imagem_final)

        img_w, img_h = 1080, 960
        imagem_noticia_resized = imagem_noticia.resize((img_w, img_h), Image.Resampling.LANCZOS)
        imagem_final.paste(imagem_noticia_resized, (0, 0))

        logo.thumbnail((300, 300))
        pos_logo_x = (IMG_WIDTH - logo.width) // 2
        pos_logo_y = 960 - (logo.height // 2)
        imagem_final.paste(logo, (pos_logo_x, pos_logo_y), logo)

        y_cursor = 960 + (logo.height // 2) + 60
        
        texto_categoria = categoria.upper()
        cat_bbox = draw.textbbox((0, 0), texto_categoria, font=fonte_categoria)
        text_width, text_height = cat_bbox[2] - cat_bbox[0], cat_bbox[3] - cat_bbox[1]
        banner_width, banner_height = text_width + 80, text_height + 40
        banner_x0 = (IMG_WIDTH - banner_width) // 2
        banner_y0 = y_cursor
        draw.rectangle([banner_x0, banner_y0, banner_x0 + banner_width, banner_y0 + banner_height], fill=cor_vermelha)
        draw.text((IMG_WIDTH / 2, banner_y0 + (banner_height / 2)), texto_categoria, font=fonte_categoria, fill=cor_branca, anchor="mm")
        y_cursor += banner_height + 40

        linhas_texto = textwrap.wrap(titulo_post.upper(), width=25)
        texto_junto = "\n".join(linhas_texto)
        draw.text((IMG_WIDTH / 2, y_cursor), texto_junto, font=fonte_titulo, fill=cor_branca, anchor="ma", align="center")

        buffer_saida = io.BytesIO()
        imagem_final.convert('RGB').save(buffer_saida, format='PNG')
        print("✅ [ETAPA 1/4] Imagem criada com sucesso!")
        return buffer_saida.getvalue()
    except Exception as e:
        print(f"❌ [ERRO] Falha na criação da imagem: {e}")
        return None

def criar_e_upar_video(imagem_bytes):
    print("🎥 [ETAPA 2/4] Criando vídeo localmente com FFmpeg...")
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_image:
            tmp_image.write(imagem_bytes)
            tmp_image_path = tmp_image.name

        tmp_video_path = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4').name
        audio_path = "audio_fundo.mp3"

        comando = [
            'ffmpeg', '-loop', '1', '-i', tmp_image_path,
            '-i', audio_path, '-c:v', 'libx264', '-t', '10',
            '-pix_fmt', 'yuv420p', '-vf', 'scale=1080:1920',
            '-shortest', '-y', tmp_video_path
        ]
        
        subprocess.run(comando, check=True, capture_output=True, text=True)
        print("  - Vídeo criado com sucesso.")

        print("☁️ [ETAPA 3/4] Fazendo upload do VÍDEO FINAL para o Cloudinary...")
        resultado = cloudinary.uploader.upload(
            tmp_video_path,
            resource_type="video",
            public_id=f"reel_final_{os.path.basename(tmp_video_path)}"
        )
        url_segura = resultado.get('secure_url')
        if not url_segura:
            raise ValueError("Cloudinary não retornou uma URL segura.")
        
        print(f"✅ [ETAPA 3/4] Upload concluído! URL: {url_segura}")
        return url_segura
    except Exception as e:
        print(f"❌ [ERRO] Falha na criação ou upload do vídeo: {e}")
        return None
    finally:
        if 'tmp_image_path' in locals() and os.path.exists(tmp_image_path):
            os.remove(tmp_image_path)
        if 'tmp_video_path' in locals() and os.path.exists(tmp_video_path):
            os.remove(tmp_video_path)

# ==============================================================================
# BLOCO 3: FUNÇÕES DE PUBLICAÇÃO
# ==============================================================================
def publicar_reel(video_url, legenda):
    print("📤 [ETAPA 4/4] Publicando Reels no Instagram e Facebook...")
    resultados = {'instagram': 'falha', 'facebook': 'falha'}
    
    # --- Instagram ---
    try:
        print("\n--- TENTANDO PUBLICAR NO INSTAGRAM ---")
        url_container_ig = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ID}/media"
        params_ig = {'media_type': 'REELS', 'video_url': video_url, 'caption': legenda, 'access_token': META_API_TOKEN}
        r_container_ig = requests.post(url_container_ig, params=params_ig, timeout=45)
        print(f"  - [IG] Resposta da Criação do Contêiner: Status {r_container_ig.status_code} | Resposta: {r_container_ig.text}")
        r_container_ig.raise_for_status()
        id_criacao_ig = r_container_ig.json()['id']
        print(f"  - [IG] Contêiner de mídia criado: {id_criacao_ig}")

        url_publicacao_ig = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ID}/media_publish"
        params_publicacao_ig = {'creation_id': id_criacao_ig, 'access_token': META_API_TOKEN}
        
        for i in range(12):
            print(f"  - [IG] Verificando status do upload (tentativa {i+1}/12)...")
            r_publish_ig = requests.post(url_publicacao_ig, params=params_publicacao_ig, timeout=45)
            print(f"  - [IG] Resposta da Publicação: Status {r_publish_ig.status_code} | Resposta: {r_publish_ig.text}")
            if r_publish_ig.status_code == 200:
                print("  - ✅ [IG] Reel publicado com sucesso!")
                resultados['instagram'] = 'sucesso'
                break
            
            error_info = r_publish_ig.json().get('error', {})
            if error_info.get('code') == 9007:
                print("  - [IG] Vídeo ainda processando, aguardando 10s...")
                time.sleep(10)
            else:
                raise requests.exceptions.HTTPError(response=r_publish_ig)
        else:
             print("  - ❌ [IG] Tempo de processamento do vídeo esgotado.")
             resultados['instagram'] = 'falha_timeout'

    except Exception as e:
        print(f"  - ❌ [IG] FALHA GERAL AO PUBLICAR: {e}")

    # --- Facebook ---
    try:
        print("\n--- TENTANDO PUBLICAR NO FACEBOOK ---")
        url_post_fb = f"https://graph.facebook.com/v19.0/{FACEBOOK_PAGE_ID}/videos"
        params_fb = {'file_url': video_url, 'description': legenda, 'access_token': META_API_TOKEN}
        r_fb = requests.post(url_post_fb, params=params_fb, timeout=180)
        print(f"  - [FB] Resposta da Publicação: Status {r_fb.status_code} | Resposta: {r_fb.text}")
        r_fb.raise_for_status()
        print("  - ✅ [FB] Reel publicado com sucesso!")
        resultados['facebook'] = 'sucesso'
    except Exception as e:
        print(f"  - ❌ [FB] FALHA GERAL AO PUBLICAR: {e}")
        
    return resultados

# ==============================================================================
# BLOCO 4: O MAESTRO (RECEPTOR DO WEBHOOK)
# ==============================================================================
@app.route('/webhook-boca', methods=['POST'])
def webhook_receiver():
    print("\n" + "="*50)
    print("🔔 [WEBHOOK] Webhook para REEL recebido!")
    
    try:
        time.sleep(5)

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
        print(f"❌ [ERRO CRÍTICO] Falha ao processar dados: {e}")
        return jsonify({"status": "erro_processamento_wp", "message": str(e)}), 500

    imagem_bytes = criar_imagem_reel(url_imagem_destaque, titulo_noticia, categoria)
    if not imagem_bytes: return jsonify({"status": "erro_criacao_imagem"}), 500
    
    url_video_publica = criar_e_upar_video(imagem_bytes)
    if not url_video_publica: return jsonify({"status": "erro_criacao_video"}), 500

    resumo_curto = (resumo_noticia[:150] + '...') if len(resumo_noticia) > 150 else resumo_noticia
    legenda_final = f"{titulo_noticia.upper()}\n\n{resumo_curto}\n\nLeia a matéria completa!\n\n#noticias #{categoria.replace(' ', '').lower()} #litoralnorte"
    
    resultados = publicar_reel(url_video_publica, legenda_final)

    if resultados['instagram'] == 'sucesso' or resultados['facebook'] == 'sucesso':
        print("🎉 [SUCESSO] Automação concluída com pelo menos uma publicação!")
        return jsonify({"status": "sucesso", "resultados": resultados}), 200
    else:
        print("😭 [FALHA] Nenhuma publicação foi bem-sucedida.")
        return jsonify({"status": "falha_publicacao", "resultados": resultados}), 500

# ==============================================================================
# BLOCO 5: INICIALIZAÇÃO
# ==============================================================================
@app.route('/')
def health_check():
    return "Serviço de automação de REELS v16.0 está no ar.", 200

if __name__ == '__main__':
    if any(not os.getenv(var) for var in ['WP_URL', 'WP_USER', 'WP_PASSWORD', 'USER_ACCESS_TOKEN', 'INSTAGRAM_ID', 'FACEBOOK_PAGE_ID', 'CLOUDINARY_CLOUD_NAME', 'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET']):
        print("❌ ERRO CRÍTICO: Faltando uma ou mais variáveis de ambiente. A aplicação não pode iniciar.")
        exit(1)
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
