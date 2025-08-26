# ==============================================================================
# BOCA_APP.PY — WP -> IMG -> VÍDEO (MP4) -> CLOUDINARY (video/upload) -> REELS
# ==============================================================================
import os
import io
import time
import textwrap
import tempfile
import subprocess
import requests
from base64 import b64encode
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

import cloudinary
import cloudinary.uploader
import cloudinary.api
from cloudinary.utils import cloudinary_url

# ------------------------------------------------------------------------------
# INICIALIZAÇÃO
# ------------------------------------------------------------------------------
load_dotenv()
print("🚀 INICIANDO AUTOMAÇÃO DE REELS v14.0 (Render + Cloudinary Vídeo + Reels)")

# WordPress
WP_URL = os.getenv('WP_URL')
WP_USER = os.getenv('WP_USER')
WP_PASSWORD = os.getenv('WP_PASSWORD')

# Meta / Facebook
META_API_TOKEN = os.getenv('USER_ACCESS_TOKEN')
FACEBOOK_PAGE_ID = os.getenv('FACEBOOK_PAGE_ID')

# Cloudinary
CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME')
CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET')

# Variáveis obrigatórias
required_vars = [
    'WP_URL', 'WP_USER', 'WP_PASSWORD',
    'USER_ACCESS_TOKEN', 'FACEBOOK_PAGE_ID',
    'CLOUDINARY_CLOUD_NAME', 'CLOUDINARY_API_KEY', 'CLOUDINARY_API_SECRET'
]

# WP Headers
credentials = f"{WP_USER}:{WP_PASSWORD}"
token_wp = b64encode(credentials.encode())
HEADERS_WP = {'Authorization': f'Basic {token_wp.decode("utf-8")}'}

# Cloudinary config
cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True
)

# Persistência no Render
PROCESSED_IDS_FILE = '/var/data/processed_post_ids.txt'


# ------------------------------------------------------------------------------
# AUXILIARES (IDs processados)
# ------------------------------------------------------------------------------
def get_processed_ids():
    try:
        if not os.path.exists(PROCESSED_IDS_FILE):
            os.makedirs(os.path.dirname(PROCESSED_IDS_FILE), exist_ok=True)
            return set()
        with open(PROCESSED_IDS_FILE, 'r') as f:
            return set(line.strip() for line in f if line.strip())
    except Exception as e:
        print(f"  - Aviso: não foi possível ler IDs processados: {e}")
        return set()

def add_processed_id(post_id):
    try:
        os.makedirs(os.path.dirname(PROCESSED_IDS_FILE), exist_ok=True)
        with open(PROCESSED_IDS_FILE, 'a') as f:
            f.write(f"{post_id}\n")
    except Exception as e:
        print(f"  - Aviso: não foi possível salvar ID {post_id}: {e}")


# ------------------------------------------------------------------------------
# MÍDIA — capa do reel (imagem)
# ------------------------------------------------------------------------------
def criar_imagem_reel(url_imagem_noticia, titulo_post, categoria, post_id):
    print(f"🎨 [ID: {post_id}] Criando imagem base...")
    try:
        rimg = requests.get(url_imagem_noticia, stream=True, timeout=20)
        rimg.raise_for_status()
        imagem_noticia = Image.open(io.BytesIO(rimg.content)).convert("RGBA")

        logo = Image.open("logo_boca.png").convert("RGBA")
        fonte_categoria = ImageFont.truetype("Anton-Regular.ttf", 70)
        fonte_titulo = ImageFont.truetype("Roboto-Black.ttf", 72)

        IMG_W, IMG_H = 1080, 1920
        cor_fundo = (0, 0, 0, 255)
        cor_vermelha = "#e50000"
        cor_branca = "#ffffff"

        img_final = Image.new('RGBA', (IMG_W, IMG_H), cor_fundo)
        draw = ImageDraw.Draw(img_final)

        # Foto topo 1080x960
        imagem_noticia = imagem_noticia.resize((1080, 960), Image.Resampling.LANCZOS)
        img_final.paste(imagem_noticia, (0, 0))

        # Logo central (sobre a dobra)
        logo.thumbnail((300, 300))
        pos_logo_x = (IMG_W - logo.width) // 2
        pos_logo_y = 960 - (logo.height // 2)
        img_final.paste(logo, (pos_logo_x, pos_logo_y), logo)

        # Categoria
        y = 960 + (logo.height // 2) + 60
        texto_categoria = (categoria or "Notícias").upper()
        cat_bbox = draw.textbbox((0, 0), texto_categoria, font=fonte_categoria)
        tw, th = cat_bbox[2]-cat_bbox[0], cat_bbox[3]-cat_bbox[1]
        bw, bh = tw + 80, th + 40
        bx = (IMG_W - bw) // 2
        by = y
        draw.rectangle([bx, by, bx + bw, by + bh], fill=cor_vermelha)
        draw.text((IMG_W/2, by + (bh/2)), texto_categoria, font=fonte_categoria, fill=cor_branca, anchor="mm")
        y += bh + 40

        # Título
        linhas = textwrap.wrap((titulo_post or "").upper(), width=25)
        texto = "\n".join(linhas)
        draw.text((IMG_W/2, y), texto, font=fonte_titulo, fill=cor_branca, anchor="ma", align="center")

        buf = io.BytesIO()
        img_final.convert('RGB').save(buf, format='PNG')
        print(f"✅ [ID: {post_id}] Imagem criada.")
        return buf.getvalue()

    except Exception as e:
        print(f"❌ [ID: {post_id}] Erro ao criar imagem: {e}")
        return None


# ------------------------------------------------------------------------------
# VÍDEO — render MP4 + upload Cloudinary (sempre video/upload)
# ------------------------------------------------------------------------------
def criar_e_upar_video(imagem_bytes, post_id):
    print(f"🎥 [ID: {post_id}] Criando e subindo o vídeo...")

    # FFmpeg?
    try:
        subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True, text=True)
        print("✅ FFmpeg disponível.")
    except Exception:
        print("❌ FFmpeg não encontrado. Verifique Dockerfile/Build.")
        return None

    tmp_img = tmp_mp4 = None
    try:
        # Salvar imagem temporária
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as timg:
            timg.write(imagem_bytes)
            tmp_img = timg.name

        # Render MP4 1080x1920 com/sem áudio
        tmp_mp4 = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4').name
        audio_path = "audio_fundo.mp3"
        if os.path.exists(audio_path):
            cmd = [
                'ffmpeg', '-y',
                '-loop', '1', '-i', tmp_img,
                '-i', audio_path,
                '-vf', 'scale=1080:1920',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-b:a', '128k',
                '-t', '10', '-shortest',
                tmp_mp4
            ]
        else:
            print("⚠️ Sem trilha (audio_fundo.mp3 não encontrado).")
            cmd = [
                'ffmpeg', '-y',
                '-loop', '1', '-i', tmp_img,
                '-vf', 'scale=1080:1920',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                '-t', '10',
                tmp_mp4
            ]

        subprocess.run(cmd, check=True, capture_output=True, text=True)
        size = os.path.getsize(tmp_mp4)
        print(f"  - MP4 gerado: {size/1024:.1f} KB")
        if size < 100 * 1024:
            print("❌ MP4 muito pequeno. FFmpeg pode ter falhado.")
            return None

        # Upload como VÍDEO (sempre)
        print("☁️ Enviando ao Cloudinary como VÍDEO...")
        up = cloudinary.uploader.upload_large(
            tmp_mp4,
            resource_type="video",
            type="upload",
            public_id=f"reel_final_{post_id}",
            format="mp4",
            chunk_size=20_000_000,
            overwrite=True,
            invalidate=True
        )
        public_id = up.get("public_id") or f"reel_final_{post_id}"

        # Forçar URL final .mp4 de video/upload
        final_url, _ = cloudinary_url(
            public_id,
            resource_type="video",
            type="upload",
            format="mp4",
            secure=True
        )
        print(f"  - Cloudinary public_id: {public_id}")
        print(f"  - URL final construída: {final_url}")
        if "/video/upload/" not in final_url or not final_url.endswith(".mp4"):
            print("❌ URL final não é vídeo .mp4 em /video/upload/.")
            return None

        print(f"✅ Upload OK: {final_url}")
        return final_url

    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg erro:\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}")
        return None
    except Exception as e:
        print(f"❌ Erro na criação/upload: {e}")
        return None
    finally:
        for p in (tmp_img, tmp_mp4):
            try:
                if p and os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass


# ------------------------------------------------------------------------------
# SANIDADE — validar URL do vídeo (HEAD + Accept-Ranges)
# ------------------------------------------------------------------------------
def validar_url_video(url):
    """Confere se a URL é um MP4 público com suporte a range (necessário pra Graph)."""
    try:
        h = requests.head(url, timeout=25, allow_redirects=True)
        ct = h.headers.get("Content-Type", "")
        ar = h.headers.get("Accept-Ranges", "")
        ok_path = ("/video/upload/" in url) and url.endswith(".mp4")
        ok_ct = ("video" in ct) or url.endswith(".mp4")
        ok_range = ("bytes" in (ar or "").lower())
        if h.status_code == 200 and ok_path and ok_ct and ok_range:
            return True
        print(f"⚠️ HEAD {h.status_code} CT={ct} Range={ar} URL_ok={ok_path}")
        return False
    except Exception as e:
        print("❌ Falha no HEAD do vídeo:", e)
        return False


# ------------------------------------------------------------------------------
# PUBLICAÇÃO — Reels (preferencial) + fallback rascunho de vídeo
# ------------------------------------------------------------------------------
def publicar_reel_pagina(video_url, legenda, post_id):
    """
    Publica como REEL na Página.
    Permissões do token: pages_read_engagement, pages_manage_posts, pages_read_user_content,
    pages_show_list, pages_manage_metadata (e, às vezes, pages_manage_videos).
    """
    print(f"🎬 [ID: {post_id}] Publicando como REEL na Página...")
    try:
        url_reels = f"https://graph.facebook.com/v19.0/{FACEBOOK_PAGE_ID}/video_reels"
        params = {
            "video_url": video_url,     # file_url remoto
            "description": legenda,
            "access_token": META_API_TOKEN
        }
        r = requests.post(url_reels, data=params, timeout=600)
        print(f"  - [REELS] Status {r.status_code} | {r.text[:400]}")
        r.raise_for_status()
        data = r.json()
        reel_id = data.get("id")
        if reel_id:
            print(f"✅ Reel criado! ID: {reel_id}")
            return True
        print("⚠️ Resposta sem ID de reel.")
        return False
    except Exception as e:
        print(f"❌ Erro ao publicar reel: {e}")
        return False

def criar_rascunho_no_facebook(video_url, legenda, post_id):
    print(f"📤 [ID: {post_id}] Criando RASCUNHO de VÍDEO na Página...")
    try:
        url_post_video = f"https://graph.facebook.com/v19.0/{FACEBOOK_PAGE_ID}/videos"
        params = {
            'file_url': video_url,
            'description': legenda,
            'access_token': META_API_TOKEN,
            'unpublished_content_type': 'DRAFT'
        }
        r = requests.post(url_post_video, params=params, timeout=600)
        print(f"  - [FB VIDEO] Status {r.status_code} | {r.text[:400]}")
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"❌ ERRO ao criar rascunho: {e}")
        return False


# ------------------------------------------------------------------------------
# LÓGICA PRINCIPAL
# ------------------------------------------------------------------------------
def main():
    print("\n" + "=" * 50)
    print(f"Iniciando verificação de novos posts - {time.ctime()}")

    # Validar envs
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"❌ ERRO CRÍTICO: faltando variáveis -> {', '.join(missing_vars)}")
        return

    processed_ids = get_processed_ids()
    print(f"  - {len(processed_ids)} posts já processados.")

    try:
        url_api_posts = f"{WP_URL}/wp-json/wp/v2/posts?per_page=5&orderby=date"
        rp = requests.get(url_api_posts, headers=HEADERS_WP, timeout=25)
        rp.raise_for_status()
        latest_posts = rp.json()

        novos = 0
        for post in latest_posts:
            post_id = str(post.get('id'))
            if post_id in processed_ids:
                continue
            novos += 1
            print(f"\n--- NOVO POST: ID {post_id} ---")

            titulo = BeautifulSoup(post.get('title', {}).get('rendered', ''), 'html.parser').get_text()
            resumo = BeautifulSoup(post.get('excerpt', {}).get('rendered', ''), 'html.parser').get_text(strip=True)

            # Categoria
            categoria = "Notícias"
            if post.get('categories'):
                try:
                    id_cat = post['categories'][0]
                    rcat = requests.get(f"{WP_URL}/wp-json/wp/v2/categories/{id_cat}", headers=HEADERS_WP, timeout=12)
                    rcat.raise_for_status()
                    categoria = rcat.json().get('name', 'Notícias')
                except Exception as e:
                    print("  - Aviso (categoria):", e)

            # Imagem destacada OU primeira imagem do conteúdo
            url_img = None
            fid = post.get('featured_media')
            if fid:
                try:
                    rmedia = requests.get(f"{WP_URL}/wp-json/wp/v2/media/{fid}", headers=HEADERS_WP, timeout=15)
                    rmedia.raise_for_status()
                    url_img = rmedia.json().get('source_url')
                except Exception as e:
                    print("  - Aviso (mídia destacada):", e)

            if not url_img:
                html = post.get('content', {}).get('rendered', '')
                soup = BeautifulSoup(html, 'html.parser')
                fimg = soup.find('img')
                if fimg and fimg.get('src'):
                    url_img = fimg['src']

            if not url_img:
                print("  - ⚠️ Post sem imagem. Pulando.")
                add_processed_id(post_id)
                continue

            # 1) Arte
            img_bytes = criar_imagem_reel(url_img, titulo, categoria, post_id)
            if not img_bytes:
                add_processed_id(post_id)
                continue

            # 2) Vídeo MP4 + Cloudinary (video/upload)
            url_mp4 = criar_e_upar_video(img_bytes, post_id)
            if not url_mp4:
                add_processed_id(post_id)
                continue

            # 3) Sanidade da URL (HEAD + Range)
            if not validar_url_video(url_mp4):
                print("  - ⚠️ URL MP4 reprovada na validação. Pulando publicação.")
                add_processed_id(post_id)
                continue

            # 4) Legenda
            resumo_curto = (resumo[:2200] + '...') if len(resumo) > 2200 else resumo
            legenda = (
                f"{titulo.upper()}\n\n"
                f"{resumo_curto}\n\n"
                f"Leia a matéria completa!\n\n"
                f"#noticias #{categoria.replace(' ', '').lower()} #litoralnorte"
            )

            # 5) Publicar como REEL (preferência), com fallback para rascunho de vídeo
            ok = publicar_reel_pagina(url_mp4, legenda, post_id)
            if not ok:
                print("  - Tentando fallback: rascunho de vídeo na Página...")
                ok = criar_rascunho_no_facebook(url_mp4, legenda, post_id)

            if ok:
                print(f"  - Marcando ID {post_id} como processado.")
                add_processed_id(post_id)

        if novos == 0:
            print("  - Nenhum post novo encontrado.")

    except Exception as e:
        print(f"❌ [ERRO CRÍTICO] Falha geral: {e}")

    print(f"Verificação concluída - {time.ctime()}")
    print("=" * 50 + "\n")


# ------------------------------------------------------------------------------
# LOOP CONTÍNUO (CRON INTERNO)
# ------------------------------------------------------------------------------
if __name__ == '__main__':
    intervalo = int(os.getenv("CRON_INTERVAL_SECONDS", "300"))  # padrão 5 min
    while True:
        main()
        print(f"⏳ Aguardando {intervalo}s para nova checagem...")
        try:
            time.sleep(intervalo)
        except KeyboardInterrupt:
            print("Encerrando...")
            break
