from flask import Flask, request, jsonify
import os
import logging
import requests
import json
import re
import time
import subprocess
from base64 import b64encode
import tempfile
import shutil

# -- Importações para a Geração do Vídeo --
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from jinja2 import Environment, FileSystemLoader

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configurar o Jinja2 para ler templates
env = Environment(loader=FileSystemLoader('.'))

# ⚡ VARIÁVEIS DE AMBIENTE:
INSTAGRAM_ACCESS_TOKEN = os.getenv('PAGE_TOKEN_BOCA', '') or os.getenv('USER_ACCESS_TOKEN', '')
INSTAGRAM_ACCOUNT_ID = os.getenv('INSTAGRAM_ID', '')
FACEBOOK_PAGE_ID = os.getenv('FACEBOOK_PAGE_ID', '')
WP_URL = os.getenv('WP_URL', '')
WP_USER = os.getenv('WP_USER', '')
WP_PASSWORD = os.getenv('WP_PASSWORD', '')

# Configurar headers do WordPress
HEADERS_WP = {}
if WP_USER and WP_PASSWORD:
    credentials = f"{WP_USER}:{WP_PASSWORD}"
    token_wp = b64encode(credentials.encode())
    HEADERS_WP = {'Authorization': f'Basic {token_wp.decode("utf-8")}'}
    logger.info("✅ Configuração WordPress OK")
else:
    logger.warning("⚠️ Configuração WordPress incompleta")

def limpar_html(texto):
    """Remove tags HTML do texto"""
    if not texto:
        return ""
    texto_limpo = re.sub('<[^>]+>', '', texto)
    texto_limpo = texto_limpo.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
    return texto_limpo.strip()

def obter_imagem_original(post_id):
    """Obtém a imagem ORIGINAL da notícia"""
    try:
        post_url = f"{WP_URL}/wp-json/wp/v2/posts/{post_id}"
        response = requests.get(post_url, headers=HEADERS_WP, timeout=15)
        
        if response.status_code != 200:
            logger.error("❌ Erro ao buscar post")
            return None
        
        post_data = response.json()
        featured_media_id = post_data.get('featured_media')
        
        if featured_media_id:
            media_url = f"{WP_URL}/wp-json/wp/v2/media/{featured_media_id}"
            media_response = requests.get(media_url, headers=HEADERS_WP, timeout=15)
            
            if media_response.status_code == 200:
                media_data = media_response.json()
                return media_data.get('source_url')
        
        content = post_data.get('content', {}).get('rendered', '')
        if 'wp-image-' in content:
            image_match = re.search(r'src="([^"]+\.(jpg|jpeg|png))"', content)
            if image_match:
                return image_match.group(1)
        
        return None
        
    except Exception as e:
        logger.error(f"💥 Erro ao buscar imagem original: {str(e)}")
        return None

def criar_reel_video(url_imagem, titulo, hashtags, categoria):
    """
    Cria um vídeo a partir de um template HTML e dados dinâmicos.
    Retorna o caminho do arquivo .mp4 se a criação for bem-sucedida, senão None.
    """
    logger.info("🎬 Iniciando a criação do vídeo...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            logger.info("📸 Renderizando template HTML...")
            template = env.get_template('template/reel_template.html')
            
            rendered_html = template.render(
                imagem_url=url_imagem,
                titulo=titulo,
                hashtags=hashtags,
                categoria=categoria
            )

            html_path = os.path.join(tmpdir, "rendered_page.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(rendered_html)

            # --- CONFIGURAÇÃO ATUALIZADA DO SELENIUM ---
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("window-size=1080,1920")

            # LINHAS CRÍTICAS ADICIONADAS:
            chrome_binary_path = os.getenv('GOOGLE_CHROME_BIN')
            if chrome_binary_path:
                logger.info(f"Usando Chrome binary de: {chrome_binary_path}")
                chrome_options.binary_location = chrome_binary_path
            else:
                logger.warning("Variável GOOGLE_CHROME_BIN não encontrada. Usando caminho padrão.")
            # --- FIM DA ATUALIZAÇÃO ---

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)

            driver.get(f"file://{html_path}")
            time.sleep(3) 

            screenshot_path = os.path.join(tmpdir, "frame.png")
            driver.save_screenshot(screenshot_path)
            driver.quit()
            
            if not os.path.exists(screenshot_path):
                logger.error("❌ Selenium falhou ao criar a imagem")
                return None
            
            logger.info("🎥 Gerando vídeo com FFmpeg...")
            audio_path = "audio_fundo.mp3"
            output_video_path = os.path.join(tmpdir, "video_final.mp4")

            comando_ffmpeg = [
                'ffmpeg', '-loop', '1', '-i', screenshot_path,
                '-i', audio_path, '-c:v', 'libx264', '-t', '10',
                '-pix_fmt', 'yuv420p', '-vf', 'scale=1080:1920,fps=30',
                '-y', output_video_path
            ]
            
            subprocess.run(comando_ffmpeg, check=True, capture_output=True, text=True)

            if os.path.exists(output_video_path):
                caminho_final = os.path.join(os.environ.get('TMPDIR', '/tmp'), f"video_{int(time.time())}.mp4")
                shutil.copy(output_video_path, caminho_final)
                logger.info(f"✅ Vídeo criado com sucesso: {caminho_final}")
                return caminho_final
            else:
                logger.error("❌ FFmpeg não gerou o vídeo")
                return None
            
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Erro ao rodar FFmpeg: {e.stderr}")
            return None
        except Exception as e:
            logger.error(f"💥 Erro na criação do vídeo: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

def publicar_video_no_instagram(video_url, legenda):
    """
    Publica um vídeo (Reel) no Instagram a partir de uma URL pública.
    Esta função assume que o vídeo já está hospedado em algum lugar.
    """
    try:
        if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_ACCOUNT_ID:
            return {"status": "error", "message": "❌ Configuração Instagram incompleta"}

        create_url = f"https://graph.facebook.com/v18.0/{INSTAGRAM_ACCOUNT_ID}/media"
        payload = {
            'video_url': video_url,
            'media_type': 'REELS',
            'caption': legenda,
            'access_token': INSTAGRAM_ACCESS_TOKEN
        }
        
        logger.info("📦 Criando container de vídeo no Instagram...")
        response = requests.post(create_url, data=payload, timeout=60)
        result = response.json()
        
        if 'id' not in result:
            logger.error(f"❌ Erro Instagram container: {result}")
            return {"status": "error", "message": result}
        
        creation_id = result['id']
        logger.info(f"✅ Container de vídeo criado: {creation_id}")

        publish_url = f"https://graph.facebook.com/v18.0/{INSTAGRAM_ACCOUNT_ID}/media_publish"
        publish_payload = {
            'creation_id': creation_id,
            'access_token': INSTAGRAM_ACCESS_TOKEN
        }
        
        for _ in range(5):
            logger.info("🚀 Publicando o Reel...")
            publish_response = requests.post(publish_url, data=publish_payload, timeout=60)
            publish_result = publish_response.json()
            
            if 'error' in publish_result and 'temporarily unavailable' in publish_result['error'].get('message', ''):
                logger.warning("⏳ Vídeo ainda processando. Tentando novamente em 10 segundos...")
                time.sleep(10)
            elif 'id' in publish_result:
                logger.info(f"🎉 Instagram OK! ID: {publish_result['id']}")
                return {"status": "success", "id": publish_result['id']}
            else:
                logger.error(f"❌ Erro Instagram publicação: {publish_result}")
                return {"status": "error", "message": publish_result}

        logger.error("❌ Tentativas de publicação esgotadas.")
        return {"status": "error", "message": "Tentativas de publicação esgotadas."}
        
    except Exception as e:
        logger.error(f"💥 Erro Instagram: {str(e)}")
        return {"status": "error", "message": str(e)}

def publicar_reel_no_facebook(video_url, legenda):
    """
    Publica um vídeo (Reel) em uma Página do Facebook a partir de uma URL pública.
    """
    logger.info("📢 Publicando Reel no Facebook...")
    try:
        if not INSTAGRAM_ACCESS_TOKEN or not FACEBOOK_PAGE_ID:
            logger.error("❌ Configuração do Facebook incompleta.")
            return {"status": "error", "message": "Configuração do Facebook incompleta"}

        post_url = f"https://graph.facebook.com/v18.0/{FACEBOOK_PAGE_ID}/videos"
        
        payload = {
            'file_url': video_url,
            'description': legenda,
            'access_token': INSTAGRAM_ACCESS_TOKEN
        }
        
        response = requests.post(post_url, data=payload, timeout=180)
        result = response.json()
        
        if 'id' in result:
            logger.info(f"🎉 Facebook OK! ID do Post: {result['id']}")
            return {"status": "success", "id": result['id']}
        else:
            logger.error(f"❌ Erro na publicação do Facebook: {result}")
            return {"status": "error", "message": result}

    except Exception as e:
        logger.error(f"💥 Erro inesperado ao publicar no Facebook: {str(e)}")
        return {"status": "error", "message": str(e)}

@app.route('/webhook-boca', methods=['POST'])
def handle_webhook():
    """Endpoint para receber webhooks do WordPress e processar."""
    try:
        data = request.json
        logger.info("🌐 Webhook recebido do WordPress")
        
        post_id = data.get('post_id')
        if not post_id:
            return jsonify({"status": "error", "message": "❌ post_id não encontrado"}), 400
        
        # 🖼️ Buscando a imagem original
        imagem_url = obter_imagem_original(post_id)
        if not imagem_url:
            return jsonify({
                "status": "error", 
                "message": "Nenhuma imagem encontrada para a notícia"
            }), 404

        # 📝 Dados para publicação
        titulo = limpar_html(data.get('post', {}).get('post_title', 'Título da notícia'))
        resumo = limpar_html(data.get('post', {}).get('post_excerpt', 'Resumo da notícia'))
        
        # Tentando buscar a categoria
        categoria = "Notícias"
        if 'post' in data and 'terms' in data['post'] and 'category' in data['post']['terms']:
            terms = data['post']['terms']['category']
            if terms:
                categoria = terms[0]['name']

        hashtags = f"#{categoria.replace(' ', '')} #litoralnorte"
        legenda = f"{titulo}\n\n{resumo}\n\nLeia a matéria completa!\n\n{hashtags}"
        
        # 🎬 GERAR O VÍDEO
        caminho_video_temporario = criar_reel_video(imagem_url, titulo, hashtags, categoria)

        if caminho_video_temporario:
            logger.info("✅ Vídeo criado com sucesso. Próximo passo: publicação.")
            
            # --- ATENÇÃO ---
            # Aqui você precisa da sua lógica para fazer upload do vídeo
            # para um serviço público (Cloudinary, S3, etc.) e obter a URL.
            # video_url_publica = fazer_upload_para_cloudinary(caminho_video_temporario)
            # Para o exemplo, vamos usar uma URL placeholder:
            video_url_publica = 'URL_DO_VIDEO_PUBLICO_AQUI'

            if not video_url_publica or video_url_publica == 'URL_DO_VIDEO_PUBLICO_AQUI':
                 return jsonify({
                    "status": "error", 
                    "message": "❌ URL do vídeo pública não foi gerada. Verifique a função de upload."
                }), 500

            # --- Dispara as publicações ---
            resultados = {}
            
            # 1. Publicar no Instagram
            resultado_instagram = publicar_video_no_instagram(video_url_publica, legenda)
            resultados['instagram'] = resultado_instagram

            # 2. Publicar no Facebook
            resultado_facebook = publicar_reel_no_facebook(video_url_publica, legenda)
            resultados['facebook'] = resultado_facebook
            
            # Resposta final
            return jsonify({
                "status": "success",
                "message": "Processo de publicação finalizado.",
                "resultados": resultados
            })
            
        else:
            return jsonify({
                "status": "error", 
                "message": "❌ Falha na criação do vídeo"
            }), 500
            
    except Exception as e:
        logger.error(f"💥 Erro no webhook: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/')
def index():
    """Página inicial com status"""
    instagram_ok = bool(INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID)
    return f"""
    <h1>🔧 Status do Sistema Boca no Trombone</h1>
    <p><b>Instagram:</b> {instagram_ok and '✅ Configurado' or '❌ Não configurado'}</p>
    <p><b>Estratégia:</b> Recebe imagem, gera vídeo e publica como Reel</p>
    <p><b>Endpoint:</b> <code>/webhook-boca</code></p>
    """

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info("🚀 Sistema de automação INICIADO!")
    app.run(host='0.0.0.0', port=port, debug=False)
