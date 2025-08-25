# ==============================================================================
# BLOCO 1: IMPORTAÇÕES E CONFIGURAÇÃO
# ==============================================================================
import os
import io
import requests
import textwrap
import time
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from base64 import b64encode
import cloudinary
import cloudinary.uploader
import cloudinary.api

load_dotenv()

print("🚀 INICIANDO AUTOMAÇÃO DE REELS v13.0 (CRON JOB DEFINITIVO)")

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

# Lista de variáveis obrigatórias para a aplicação funcionar
required_vars = [
    'WP_URL', 'WP_USER', 'WP_PASSWORD', 'USER_ACCESS_TOKEN', 'INSTAGRAM_ID',
    'FACEBOOK_PAGE_ID', 'CLOUDINARY_CLOUD_NAME', 'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET'
]

# Configurar headers e Cloudinary
credentials = f"{WP_USER}:{WP_PASSWORD}"
token_wp = b64encode(credentials.encode())
HEADERS_WP = {'Authorization': f'Basic {token_wp.decode("utf-8")}'}
cloudinary.config(cloud_name=CLOUDINARY_CLOUD_NAME, api_key=CLOUDINARY_API_KEY, api_secret=CLOUDINARY_API_SECRET)

# Caminho para o arquivo que armazena os IDs dos posts processados
# O Render nos dá um disco persistente em /var/data/
PROCESSED_IDS_FILE = '/var/data/processed_post_ids.txt'

# ==============================================================================
# BLOCO 2: FUNÇÕES AUXILIARES
# ==============================================================================
def get_processed_ids():
    """Lê os IDs do arquivo de log para evitar duplicatas."""
    try:
        if not os.path.exists(PROCESSED_IDS_FILE):
            return set()
        with open(PROCESSED_IDS_FILE, 'r') as f:
            return set(line.strip() for line in f)
    except Exception as e:
        print(f"  - Aviso: Não foi possível ler o arquivo de IDs processados: {e}")
        return set()

def add_processed_id(post_id):
    """Adiciona um ID ao arquivo de log após o processamento."""
    try:
        with open(PROCESSED_IDS_FILE, 'a') as f:
            f.write(f"{post_id}\n")
    except Exception as e:
        print(f"  - Aviso: Não foi possível salvar o ID {post_id} no arquivo: {e}")

# ==============================================================================
# BLOCO 3: FUNÇÕES DE MÍDIA (JÁ VALIDADAS)
# ==============================================================================
def criar_imagem_reel(url_imagem_noticia, titulo_post, categoria, post_id):
    print(f"🎨 [ID: {post_id}] Criando imagem base...")
    try:
        response_img = requests.get(url_imagem_noticia, stream=True, timeout=15)
        response_img.raise_for_status()
        imagem_noticia = Image.open(io.BytesIO(response_img.content)).convert("RGBA")
        logo = Image.open("logo_boca.png").convert("RGBA")

        IMG_WIDTH, IMG_HEIGHT = 1080, 1920
        cor_fundo = (0, 0, 0, 255); cor_vermelha = "#e50000"; cor_branca = "#ffffff"
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
        print(f"✅ [ID: {post_id}] Imagem criada com sucesso!")
        return buffer_saida.getvalue()
    except Exception as e:
        print(f"❌ [ID: {post_id}] ERRO na criação da imagem: {e}")
        return None

def construir_url_video_cloudinary(bytes_imagem, post_id):
    print(f"☁️ [ID: {post_id}] Subindo imagem e construindo URL de vídeo...")
    try:
        upload_result = cloudinary.uploader.upload(bytes_imagem, resource_type="image")
        public_id = upload_result.get('public_id')
        
        transformation_string = "du_10,l_video:audio_fundo,fl_layer_apply"
        video_url = cloudinary.utils.cloudinary_url(
            public_id, resource_type="video", 
            transformation=[{'raw_transformation': transformation_string}], secure=True
        )[0]
        
        print(f"✅ [ID: {post_id}] URL de vídeo construída: {video_url}")
        return video_url
    except Exception as e:
        print(f"❌ [ID: {post_id}] ERRO no Cloudinary: {e}")
        return None

def criar_rascunho_no_facebook(video_url, legenda, post_id):
    print(f"📤 [ID: {post_id}] Criando RASCUNHO na Página do Facebook...")
    try:
        url_post_video = f"https://graph.facebook.com/v19.0/{FACEBOOK_PAGE_ID}/videos"
        params = {
            'file_url': video_url, 'description': legenda,
            'access_token': META_API_TOKEN, 'unpublished_content_type': 'DRAFT'
        }
        r = requests.post(url_post_video, params=params, timeout=180)
        print(f"  - [FB] Resposta da API: Status {r.status_code} | Resposta: {r.text}")
        r.raise_for_status()
        print(f"✅ [ID: {post_id}] Rascunho criado com sucesso!")
        return True
    except Exception as e:
        print(f"❌ [ID: {post_id}] ERRO ao criar rascunho: {e}")
        return False

# ==============================================================================
# BLOCO 4: O MAESTRO (LÓGICA PRINCIPAL DO CRON JOB)
# ==============================================================================
def main():
    print("\n" + "="*50)
    print(f"Iniciando verificação de novos posts - {time.ctime()}")
    
    # Verifica se todas as variáveis de ambiente necessárias estão presentes.
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"❌ ERRO CRÍTICO: As seguintes variáveis de ambiente estão faltando: {', '.join(missing_vars)}. A aplicação não pode continuar.")
        return # Termina a execução se faltar configuração

    processed_ids = get_processed_ids()
    print(f"  - {len(processed_ids)} posts já foram processados anteriormente.")
    
    try:
        # Busca os 5 posts mais recentes do WordPress para verificar
        url_api_posts = f"{WP_URL}/wp-json/wp/v2/posts?per_page=5&orderby=date"
        response_posts = requests.get(url_api_posts, headers=HEADERS_WP, timeout=15)
        response_posts.raise_for_status()
        latest_posts = response_posts.json()
        
        new_posts_found = 0
        for post in latest_posts:
            post_id = str(post.get('id'))
            
            if post_id in processed_ids:
                continue # Pula para o próximo post se este já foi processado
            
            new_posts_found += 1
            print(f"\n--- NOVO POST ENCONTRADO: ID {post_id} ---")
            
            # Extrai os dados do post
            titulo_noticia = BeautifulSoup(post.get('title', {}).get('rendered', ''), 'html.parser').get_text()
            resumo_noticia = BeautifulSoup(post.get('excerpt', {}).get('rendered', ''), 'html.parser').get_text(strip=True)
            id_imagem_destaque = post.get('featured_media')

            if not id_imagem_destaque:
                print(f"  - ⚠️ [ID: {post_id}] Post não possui imagem de destaque. Pulando.")
                add_processed_id(post_id) # Marca como processado para não tentar de novo
                continue

            # Busca a URL da imagem e a categoria
            url_api_media = f"{WP_URL}/wp-json/wp/v2/media/{id_imagem_destaque}"
            response_media = requests.get(url_api_media, headers=HEADERS_WP, timeout=15)
            url_imagem_destaque = response_media.json().get('source_url')
            
            categoria = "Notícias"
            if post.get('categories'):
                id_categoria = post['categories'][0]
                url_api_cat = f"{WP_URL}/wp-json/wp/v2/categories/{id_categoria}"
                response_cat = requests.get(url_api_cat, headers=HEADERS_WP, timeout=15)
                categoria = response_cat.json().get('name', 'Notícias')

            # Inicia o fluxo de criação de mídia
            imagem_bytes = criar_imagem_reel(url_imagem_destaque, titulo_noticia, categoria, post_id)
            if not imagem_bytes: continue
            
            url_video_publica = construir_url_video_cloudinary(bytes_imagem, post_id)
            if not url_video_publica: continue

            resumo_curto = (resumo_noticia[:2200] + '...') if len(resumo_noticia) > 2200 else resumo_noticia
            legenda_final = f"{titulo_noticia.upper()}\n\n{resumo_curto}\n\nLeia a matéria completa!\n\n#noticias #{categoria.replace(' ', '').lower()} #litoralnorte"
            
            sucesso = criar_rascunho_no_facebook(video_url_publica, legenda_final, post_id)
            
            if sucesso:
                print(f"  - Marcando post ID {post_id} como processado.")
                add_processed_id(post_id)
        
        if new_posts_found == 0:
            print("  - Nenhum post novo para processar.")

    except Exception as e:
        print(f"❌ [ERRO CRÍTICO] Falha durante a execução do script: {e}")

    print(f"Verificação concluída - {time.ctime()}")
    print("="*50 + "\n")

# ==============================================================================
# BLOCO 5: INICIALIZAÇÃO
# ==============================================================================
if __name__ == '__main__':
    main()
