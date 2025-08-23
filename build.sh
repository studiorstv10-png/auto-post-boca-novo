#!/usr/bin/env bash
# exit on error
set -o errexit

echo "--- Iniciando processo de build robusto ---"

# 1. Instalação do Google Chrome (Método Direto e Forçado)
echo "--> Instalando dependências essenciais..."
apt-get update
apt-get install -y wget gnupg libnss3 libgconf-2-4 libfontconfig1

echo "--> Baixando o pacote oficial do Google Chrome..."
wget -q -O chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb

echo "--> Forçando a instalação do pacote .deb..."
dpkg -i chrome.deb || apt-get -fy install

echo "--> Google Chrome instalado com sucesso em: $(which google-chrome-stable)"

# 2. Instalação do FFmpeg
echo "--> Instalando FFmpeg..."
apt-get install -y ffmpeg
echo "--> FFmpeg instalado com sucesso."

# 3. Instalação das dependências Python
echo "--> Instalando pacotes Python..."
pip install -r requirements.txt

echo "--- Build finalizado com sucesso! ---"
