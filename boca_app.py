# ==============================================================================
# BOCA_APP.PY — Worker Render (WP -> IMG -> MP4 -> Cloudinary -> Reels)
# ==============================================================================
import os, io, time, textwrap, tempfile, subprocess, requests, gc
from base64 import b64encode
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFile
import cloudinary, cloudinary.uploader, cloudinary.api
from cloudinary.utils import cloudinary_url

# ---- Segurança e memória do Pillow ----
ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = 40_000_000

load_dotenv()
print("🚀 INICIANDO AUTOMAÇÃO DE REELS v16.1 (Worker leve Render)")

# ------------------------------------------------------------------------------
# ENV
# ------------------------------------------------------------------------------
WP_URL = os.getenv('WP_URL')
WP_USER = os.getenv('WP_USER')
WP_PASSWORD = os.getenv('WP_PASSWORD')
META_API_TOKEN = os.getenv('USER_ACCESS_TOKEN')
FACEBOOK_PAGE_ID = os.getenv('FACEBOOK_PAGE_ID')
CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME')
CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET')
INTERVALO = int(os.getenv("CRON_INTERVAL_SECONDS", "300"))  # 5 min padrão

required_vars = [
    'WP_URL','WP_USER','WP_PASSWORD',
    'USER_ACCESS_TOKEN','FACEBOOK_PAGE_ID',
    'CLOUDINARY_CLOUD_NAME','CLOUDINARY_API_KEY','CLOUDINARY_API_SECRET'
]

credentials = f"{WP_USER}:{WP_PASSWORD}"
token_wp = b64encode(credentials.encode()).decode("utf-8")
HEADERS_WP = {'Authorization': f'Basic {token_wp}'}

cloudinary.config(
    cloud_name=CLOUDINARY_CLOUD_NAME,
    api_key=CLOUDINARY_API_KEY,
    api_secret=CLOUDINARY_API_SECRET,
    secure=True
)

# Persistência simples no Render
PROCESSED_IDS_FILE = '/var/data/processed_post_ids.txt'

# ------------------------------------------------------------------------------
# Auxiliares de persistência
# ------------------------------------------------------------------------------
def get_processed_ids():
    try:
        if not os.path.exists(PROCESSED_IDS_FILE):
            os.makedirs(os.path.dirname(PROCESSED_IDS_FILE), exist_ok=True)
            return set()
        with open(PROCESSED_IDS_FILE, 'r') as f:
            return set(line.strip() for line in f if line.strip())
    except Exception as e:
        print("  - Aviso lendo IDs:", e)
        return set()

def add_processed_id(post_id: str):
    try:
        os.makedirs(os.path.dirname(PROCESSED_IDS_FILE), exist_ok=True)
        with open(PROCESSED_IDS_FILE, 'a') as f:
            f.write(f"{post_id}\n")
    except Exception as e:
        print("  - Aviso salvando ID:", e)

# ------------------------------------------------------------------------------
# Mídia — capa do reel
# ------------------------------------------------------------------------------
def criar_imagem_reel(url_imagem, titulo, categoria, post_id):
    print(f"🎨 [ID:{post_id}] Gerando imagem...")
    try:
        r = requests.get(url_imagem, stream=True, timeout=20)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGBA")
        logo = Image.open("logo_boca.png").convert("RGBA")
        fonte_categoria = ImageFont.truetype("Anton-Regular.ttf", 70)
        fonte_titulo = ImageFont.truetype("Roboto-Black.ttf", 72)

        W,H = 1080,1920
        canvas = Image.new("RGBA",(W,H),(0,0,0,255))
        draw = ImageDraw.Draw(canvas)

        # topo
        img = img.resize((1080,960), Image.Resampling.LANCZOS)
        canvas.paste(img,(0,0))

        # logo
        logo.thumbnail((300,300))
        lx = (W - logo.width)//2
        ly = 960 - (logo.height//2)
        canvas.paste(logo,(lx,ly),logo)

        # categoria
        y = 960 + (logo.height//2) + 60
        categoria = (categoria or "Notícias").upper()
        tw,th = draw.textlength(categoria,font=fonte_categoria), fonte_categoria.size
        bw,bh = int(tw)+80, th+40
        bx,by = (W-bw)//2, y
        draw.rectangle([bx,by,bx+bw,by+bh], fill="#e50000")
        draw.text((W/2, by+bh/2), categoria, font=fonte_categoria, fill="#ffffff", anchor="mm")
        y += bh + 40

        # título
        texto = "\n".join(textwrap.wrap((titulo or "").upper(), width=25))
        draw.text((W/2, y), texto, font=fonte_titulo, fill="#ffffff", anchor="ma", align="center")

        buf = io.BytesIO()
        canvas.convert("RGB").save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        print(f"❌ [ID:{post_id}] Erro imagem:", e)
        return None

# ------------------------------------------------------------------------------
# Vídeo — FFmpeg + Cloudinary video/upload
# ------------------------------------------------------------------------------
def criar_e_upar_video(imagem_bytes, post_id):
    print(f"🎥 [ID:{post_id}] Render MP4 + upload Cloudinary...")
    # FFmpeg disponível?
    try:
        subprocess.run(["ffmpeg","-version"], check=True, capture_output=True, text=True)
    except Exception:
        print("❌ FFmpeg não encontrado no container.")
        return None

    tmp_img = tmp_mp4 = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as timg:
            timg.write(imagem_bytes)
            tmp_img = timg.name

        tmp_mp4 = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
        audio = "audio_fundo.mp3"
        if os.path.exists(audio):
            cmd = [
                "ffmpeg","-y","-loop","1","-i",tmp_img,"-i",audio,
                "-vf","scale=1080:1920","-c:v","libx264","-pix_fmt","yuv420p",
                "-c:a","aac","-b:a","128k","-t","10","-shortest", tmp_mp4
            ]
        else:
            print("⚠️ Sem trilha (audio_fundo.mp3 ausente).")
            cmd = [
                "ffmpeg","-y","-loop","1","-i",tmp_img,
                "-vf","scale=1080:1920","-c:v","libx264","-pix_fmt","yuv420p",
                "-t","10", tmp_mp4
            ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

        size = os.path.getsize(tmp_mp4)
        print(f"  - MP4 gerado: {size/1024:.0f} KB")
        if size < 100*1024:
            print("❌ MP4 muito pequeno; render falhou.")
            return None

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
        final_url, _ = cloudinary_url(
            public_id, resource_type="video", type="upload", format="mp4", secure=True
        )
        print("  - URL Cloudinary:", final_url)
        if "/video/upload/" not in final_url or not final_url.endswith(".mp4"):
            print("❌ URL final não é vídeo .mp4 (video/upload).")
            return None
        return final_url

    except subprocess.CalledProcessError as e:
        print("❌ FFmpeg erro:\n", e.stderr[:500])
        return None
    except Exception as e:
        print("❌ Erro upload:", e)
        return None
    finally:
        for p in (tmp_img,tmp_mp4):
            try:
                if p and os.path.exists(p): os.remove(p)
            except: pass

# ------------------------------------------------------------------------------
# Sanidade — HEAD + Range
# ------------------------------------------------------------------------------
def validar_url_video(url):
    try:
        h = requests.head(url, timeout=25, allow_redirects=True)
        ct = h.headers.get("Content-Type","")
        ar = (h.headers.get("Accept-Ranges","") or "").lower()
        ok = (h.status_code==200 and "/video/upload/" in url and url.endswith(".mp4")
              and ("video" in ct or url.endswith(".mp4")) and "bytes" in ar)
        if not ok:
            print(f"⚠️ HEAD={h.status_code} CT={ct} Range={ar}")
        return ok
    except Exception as e:
        print("❌ HEAD falhou:", e)
        return False

# ------------------------------------------------------------------------------
# Publicação — Reels + fallback vídeo draft
# ------------------------------------------------------------------------------
def publicar_reel_pagina(video_url, legenda, post_id):
    print(f"🎬 [ID:{post_id}] Publicando como REEL...")
    try:
        url = f"https://graph.facebook.com/v19.0/{FACEBOOK_PAGE_ID}/video_reels"
        data = {"video_url": video_url, "description": legenda, "access_token": META_API_TOKEN}
        r = requests.post(url, data=data, timeout=600)
        print(f"  - REELS {r.status_code} | {r.text[:400]}")
        r.raise_for_status()
        return bool(r.json().get("id"))
    except Exception as e:
        print("❌ Reel erro:", e)
        return False

def criar_rascunho_video_pagina(video_url, legenda, post_id):
    print(f"📤 [ID:{post_id}] Fallback: rascunho de VÍDEO na Página...")
    try:
        url = f"https://graph.facebook.com/v19.0/{FACEBOOK_PAGE_ID}/videos"
        params = {
            "file_url": video_url, "description": legenda,
            "access_token": META_API_TOKEN, "unpublished_content_type": "DRAFT"
        }
        r = requests.post(url, params=params, timeout=600)
        print(f"  - VIDEO {r.status_code} | {r.text[:400]}")
        r.raise_for_status()
        return True
    except Exception as e:
        print("❌ Draft erro:", e)
        return False

# ------------------------------------------------------------------------------
# Principal — processa 1 post por ciclo (memória baixa)
# ------------------------------------------------------------------------------
def main():
    print("\n" + "="*48)
    print("Rodando ciclo:", time.ctime())

    missing = [v for v in required_vars if not os.getenv(v)]
    if missing:
        print("❌ Variáveis faltando:", ", ".join(missing))
        return

    processed = get_processed_ids()
    print(f"  - Processados: {len(processed)}")

    try:
        url = f"{WP_URL}/wp-json/wp/v2/posts?per_page=1&orderby=date"
        rp = requests.get(url, headers=HEADERS_WP, timeout=25)
        rp.raise_for_status()
        posts = rp.json()
        if not posts:
            print("  - Sem posts.")
            return

        post = posts[0]
        post_id = str(post.get('id'))
        if post_id in processed:
            print("  - Post já processado.")
            return

        # Título e resumo
        titulo = BeautifulSoup(post.get('title',{}).get('rendered',''), 'html.parser').get_text()
        resumo = BeautifulSoup(post.get('excerpt',{}).get('rendered',''), 'html.parser').get_text(strip=True)

        # Categoria
        categoria = "Notícias"
        if post.get('categories'):
            try:
                cat_id = post['categories'][0]
                rc = requests.get(f"{WP_URL}/wp-json/wp/v2/categories/{cat_id}", headers=HEADERS_WP, timeout=12)
                rc.raise_for_status()
                categoria = rc.json().get('name','Notícias')
            except Exception as e:
                print("  - Aviso categoria:", e)

        # Imagem destacada ou primeira do conteúdo
        url_img = None
        fid = post.get('featured_media')
        if fid:
            try:
                rm = requests.get(f"{WP_URL}/wp-json/wp/v2/media/{fid}", headers=HEADERS_WP, timeout=15)
                rm.raise_for_status()
                url_img = rm.json().get('source_url')
            except Exception as e:
                print("  - Aviso mídia:", e)
        if not url_img:
            html = post.get('content',{}).get('rendered','')
            soup = BeautifulSoup(html, 'html.parser')
            tag = soup.find('img')
            if tag and tag.get('src'):
                url_img = tag['src']
        if not url_img:
            print("  - ⚠️ Sem imagem; pulando.")
            add_processed_id(post_id); return

        # 1) Arte
        imagem_bytes = criar_imagem_reel(url_img, titulo, categoria, post_id)
        if not imagem_bytes:
            add_processed_id(post_id); return

        # 2) Vídeo + Cloudinary
        url_mp4 = criar_e_upar_video(imagem_bytes, post_id)
        del imagem_bytes; gc.collect()
        if not url_mp4:
            add_processed_id(post_id); return

        # 3) Sanidade
        if not validar_url_video(url_mp4):
            add_processed_id(post_id); return

        # 4) Legenda
        resumo_curto = (resumo[:2200] + '...') if len(resumo) > 2200 else resumo
        legenda = f"{titulo.upper()}\n\n{resumo_curto}\n\nLeia a matéria completa!\n\n#noticias #{categoria.replace(' ','').lower()} #litoralnorte"

        # 5) Publicar REEL -> fallback draft vídeo
        ok = publicar_reel_pagina(url_mp4, legenda, post_id)
        if not ok:
            ok = criar_rascunho_video_pagina(url_mp4, legenda, post_id)

        if ok:
            add_processed_id(post_id)
            print(f"✅ ID {post_id} processado com sucesso.")

    except Exception as e:
        print("❌ Erro no ciclo:", e)

    print("Ciclo concluído:", time.ctime())
    print("="*48)

# ------------------------------------------------------------------------------
# Loop do worker
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # checar ffmpeg uma vez (falha rápida)
    try:
        subprocess.run(["ffmpeg","-version"], check=True, capture_output=True, text=True)
        print("✅ FFmpeg OK.")
    except Exception:
        print("❌ FFmpeg não disponível. Verifique Dockerfile.")
    while True:
        main()
        gc.collect()
        print(f"⏳ Aguardando {INTERVALO}s...")
        try:
            time.sleep(INTERVALO)
        except KeyboardInterrupt:
            print("Encerrando worker.")
            break
