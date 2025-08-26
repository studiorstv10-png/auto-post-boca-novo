# ==============================================================================
# BOCA_APP.PY — AUTO POST REELS (WP -> IMG -> VÍDEO -> CLOUDINARY -> FB DRAFT)
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
import subprocess
import tempfile

load_dotenv()

print("🚀 INICIANDO AUTOMAÇÃO DE REELS v13.1 (Render + Cloudinary + FB Draft)")

# --- Carregar variáveis ---
WP_URL = os.getenv('WP_URL')
WP_USER = os.getenv('WP_USER')
WP_PASSWORD = os.getenv('WP_PASSWORD')

META_API_TOKEN = os.getenv('USER_ACCESS_TOKEN')
INSTAGRAM_ID = os.getenv('INSTAGRAM_ID')        # (não usado neste script, mas mantido)
FACEBOOK_PAGE_ID = os.getenv('FACEBOOK_PAGE_ID')

CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME')
CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET')

# Lista de variáveis obrigatórias
required_vars = [
    'WP_URL', 'WP_USER', 'WP_PASSWORD',
    'USER_ACCESS_TOKEN', 'FACEBOOK_PAGE_ID',
    'CLOUDINARY_CLOUD_NAME', 'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET'
]

# Configurar headers e Cloudinary
credentials = f"{WP_USER}:{WP_PASSWORD}"
token_wp = b64encode(credentials.encode())
HEADERS_WP = {'Authorization': f'Basic {token_wp.decode("utf-8")}'}

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True
)

# Disco persistente no Render
PROCESSED_IDS_FILE = '/var/data/processed_post_ids.txt'


# ==============================================================================
# BLOCO 2: FUNÇÕES AUXILIARES
# ==============================================================================
def get_processed_ids():
    """Lê os IDs já processados para evitar duplicatas."""
    try:
        if not os.path.exists(PROCESSED_IDS_FILE):
            os.makedirs(os.path.dirname(PROCESSED_IDS_FILE), exist_ok=True)
            return set()
        with open(PROCESSED_IDS_FILE, 'r') as f:
            return set(line.strip() for line in f if line.strip())
    except Exception as e:
        print(f"  - Aviso: Não foi possível ler o arquivo de IDs processados: {e}")
        return set()


def add_processed_id(post_id):
    """Adiciona um ID ao arquivo de log após o processamento."""
    try:
        os.makedirs(os.path.dirname(PROCESSED_IDS_FILE), exist_ok=True)
        with open(PROCESSED_IDS_FILE, 'a') as f:
            f.write(f"{post_id}\n")
    except Exception as e:
        print(f"  - Aviso: Não foi possível salvar o ID {post_id}: {e}")


# ==============================================================================
# BLOCO 3: FUNÇÕES DE MÍDIA
# ==============================================================================
def criar_imagem_reel(url_imagem_noticia, titulo_post, categoria, post_id):
    print(f"🎨 [ID: {post_id}] Criando imagem base...")
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

        # Topo com a foto 1080x960
        img_w, img_h = 1080, 960
        imagem_noticia_resized = imagem_noticia.resize((img_w, img_h), Image.Resampling.LANCZOS)
        imagem_final.paste(imagem_noticia_resized, (0, 0))

        # Logo central sobre a "dobradiça"
        logo.thumbnail((300, 300))
        pos_logo_x = (IMG_WIDTH - logo.width) // 2
        pos_logo_y = 960 - (logo.height // 2)
        imagem_final.paste(logo, (pos_logo_x, pos_logo_y), logo)

        # Banner da categoria
        y_cursor = 960 + (logo.height // 2) + 60
        texto_categoria = (categoria or "Notícias").upper()
        cat_bbox = draw.textbbox((0, 0), texto_categoria, font=fonte_categoria)
        text_width, text_height = cat_bbox[2] - cat_bbox[0], cat_bbox[3] - cat_bbox[1]
        banner_width, banner_height = text_width + 80, text_height + 40
        banner_x0 = (IMG_WIDTH - banner_width) // 2
        banner_y0 = y_cursor
        draw.rectangle([banner_x0, banner_y0, banner_x0 + banner_width, banner_y0 + banner_height], fill=cor_vermelha)
        draw.text((IMG_WIDTH / 2, banner_y0 + (banner_height / 2)), texto_categoria, font=fonte_categoria,
                  fill=cor_branca, anchor="mm")
        y_cursor += banner_height + 40

        # Título quebrado em linhas
        linhas_texto = textwrap.wrap((titulo_post or "").upper(), width=25)
        texto_junto = "\n".join(linhas_texto)
        draw.text((IMG_WIDTH / 2, y_cursor), texto_junto, font=fonte_titulo,
                  fill=cor_branca, anchor="ma", align="center")

        buffer_saida = io.BytesIO()
        imagem_final.convert('RGB').save(buffer_saida, format='PNG')
        print(f"✅ [ID: {post_id}] Imagem criada com sucesso!")
        return buffer_saida.getvalue()

    except Exception as e:
        print(f"❌ [ID: {post_id}] ERRO na criação da imagem: {e}")
        return None


def criar_e_upar_video(imagem_bytes, post_id):
    print(f"🎥 [ID: {post_id}] Criando e subindo o vídeo...")

    # Checar FFmpeg disponível
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True, text=True)
        print("✅ FFmpeg disponível no ambiente.")
    except Exception:
        print("❌ FFmpeg não encontrado. Verifique seu Dockerfile/Build.")
        return None

    tmp_image_path = None
    tmp_video_path = None
    try:
        # Escrever imagem temporária
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_image:
            tmp_image.write(imagem_bytes)
            tmp_image_path = tmp_image.name

        tmp_video_path = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4').name
        audio_path = "audio_fundo.mp3"

        comando = [
            'ffmpeg', '-y',
            '-loop', '1', '-i', tmp_image_path,
            '-i', audio_path,
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-vf', 'scale=1080:1920',
            '-t', '10',  # duração
            '-shortest',
            tmp_video_path
        ]

        proc = subprocess.run(comando, check=True, capture_output=True, text=True)
        print(f"  - [ID: {post_id}] Vídeo criado.")

        # Upload Cloudinary robusto (arquivos grandes / rede lenta)
        print(f"☁️ [ID: {post_id}] Enviando para Cloudinary...")
        resultado = cloudinary.uploader.upload_large(
            tmp_video_path,
            resource_type="video",
            public_id=f"reel_final_{post_id}",
            chunk_size=20_000_000  # pedaços de ~20MB
        )
        url_segura = resultado.get('secure_url')
        if not url_segura:
            raise ValueError("Cloudinary não retornou secure_url.")

        print(f"✅ [ID: {post_id}] Upload concluído! URL: {url_segura}")
        return url_segura

    except subprocess.CalledProcessError as e:
        print(f"❌ [ID: {post_id}] FFmpeg erro:\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}")
        return None
    except Exception as e:
        print(f"❌ [ID: {post_id}] ERRO na criação/upload: {e}")
        return None
    finally:
        try:
            if tmp_image_path and os.path.exists(tmp_image_path):
                os.remove(tmp_image_path)
            if tmp_video_path and os.path.exists(tmp_video_path):
                os.remove(tmp_video_path)
        except Exception:
            pass


def criar_rascunho_no_facebook(video_url, legenda, post_id):
    print(f"📤 [ID: {post_id}] Criando RASCUNHO na Página do Facebook...")
    try:
        url_post_video = f"https://graph.facebook.com/v19.0/{FACEBOOK_PAGE_ID}/videos"
        params = {
            'file_url': video_url,
            'description': legenda,
            'access_token': META_API_TOKEN,
            'unpublished_content_type': 'DRAFT'
        }
        r = requests.post(url_post_video, params=params, timeout=300)
        if r.status_code >= 400:
            print("❌ [FB] Erro:", r.status_code, r.text)
        r.raise_for_status()
        print(f"✅ [ID: {post_id}] Rascunho criado com sucesso!")
        return True
    except Exception as e:
        print(f"❌ [ID: {post_id}] ERRO ao criar rascunho: {e}")
        return False


# ==============================================================================
# BLOCO 4: LÓGICA PRINCIPAL
# ==============================================================================
def main():
    print("\n" + "=" * 50)
    print(f"Iniciando verificação de novos posts - {time.ctime()}")

    # Validar envs
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"❌ ERRO CRÍTICO: Faltando variáveis: {', '.join(missing_vars)}.")
        return

    processed_ids = get_processed_ids()
    print(f"  - {len(processed_ids)} posts já foram processados anteriormente.")

    try:
        url_api_posts = f"{WP_URL}/wp-json/wp/v2/posts?per_page=5&orderby=date"
        response_posts = requests.get(url_api_posts, headers=HEADERS_WP, timeout=20)
        response_posts.raise_for_status()
        latest_posts = response_posts.json()

        new_posts_found = 0
        for post in latest_posts:
            post_id = str(post.get('id'))
            if post_id in processed_ids:
                continue

            new_posts_found += 1
            print(f"\n--- NOVO POST ENCONTRADO: ID {post_id} ---")

            titulo_noticia = BeautifulSoup(post.get('title', {}).get('rendered', ''), 'html.parser').get_text()
            resumo_noticia = BeautifulSoup(post.get('excerpt', {}).get('rendered', ''), 'html.parser').get_text(strip=True)

            # Categoria
            categoria = "Notícias"
            if post.get('categories'):
                try:
                    id_categoria = post['categories'][0]
                    url_api_cat = f"{WP_URL}/wp-json/wp/v2/categories/{id_categoria}"
                    response_cat = requests.get(url_api_cat, headers=HEADERS_WP, timeout=10)
                    response_cat.raise_for_status()
                    categoria = response_cat.json().get('name', 'Notícias')
                except Exception as e:
                    print(f"  - Aviso: falha ao obter categoria: {e}")

            # Imagem destacada OU primeira imagem do conteúdo
            url_imagem_destaque = None
            id_imagem_destaque = post.get('featured_media')
            if id_imagem_destaque:
                try:
                    url_api_media = f"{WP_URL}/wp-json/wp/v2/media/{id_imagem_destaque}"
                    response_media = requests.get(url_api_media, headers=HEADERS_WP, timeout=15)
                    response_media.raise_for_status()
                    url_imagem_destaque = response_media.json().get('source_url')
                except Exception as e:
                    print(f"  - Aviso: falha ao obter mídia destacada: {e}")

            if not url_imagem_destaque:
                html = post.get('content', {}).get('rendered', '')
                soup = BeautifulSoup(html, 'html.parser')
                first_img = soup.find('img')
                if first_img and first_img.get('src'):
                    url_imagem_destaque = first_img['src']

            if not url_imagem_destaque:
                print(f"  - ⚠️ [ID: {post_id}] Post sem imagem. Pulando.")
                add_processed_id(post_id)
                continue

            # 1) Gera imagem com layout
            imagem_bytes = criar_imagem_reel(url_imagem_destaque, titulo_noticia, categoria, post_id)
            if not imagem_bytes:
                add_processed_id(post_id)  # evita loop eterno
                continue

            # 2) Gera vídeo + upload Cloudinary
            url_video_publica = criar_e_upar_video(imagem_bytes, post_id)
            if not url_video_publica:
                add_processed_id(post_id)
                continue

            # 3) Legenda
            resumo_curto = (resumo_noticia[:2200] + '...') if len(resumo_noticia) > 2200 else resumo_noticia
            legenda_final = (
                f"{titulo_noticia.upper()}\n\n"
                f"{resumo_curto}\n\n"
                f"Leia a matéria completa!\n\n"
                f"#noticias #{categoria.replace(' ', '').lower()} #litoralnorte"
            )

            # 4) Cria rascunho na Página do Facebook
            sucesso = criar_rascunho_no_facebook(url_video_publica, legenda_final, post_id)  # <— variável correta

            if sucesso:
                print(f"  - Marcando post ID {post_id} como processado.")
                add_processed_id(post_id)

        if new_posts_found == 0:
            print("  - Nenhum post novo para processar.")

    except Exception as e:
        print(f"❌ [ERRO CRÍTICO] Falha durante a execução do script: {e}")

    print(f"Verificação concluída - {time.ctime()}")
    print("=" * 50 + "\n")


# ==============================================================================
# BLOCO 5: LOOP CONTÍNUO
# ==============================================================================
if __name__ == '__main__':
    # loop para rodar como "daemon" no Render
    INTERVALO = int(os.getenv("CRON_INTERVAL_SECONDS", "300"))  # padrão 5 min
    while True:
        main()
        print(f"⏳ Aguardando {INTERVALO}s para nova checagem...")
        try:
            time.sleep(INTERVALO)
        except KeyboardInterrupt:
            print("Encerrando...")
            break
