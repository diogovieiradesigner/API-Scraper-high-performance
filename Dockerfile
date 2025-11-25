# Base Image oficial do Playwright (já inclui dependências e browsers)
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# Define diretório de trabalho
WORKDIR /app

# Variáveis de Ambiente
ENV PYTHONUNBUFFERED=1
ENV MAX_CONCURRENCY=20
# Garante que o Playwright use o caminho correto
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Atualiza lista de pacotes e instala dependências básicas (garantia extra)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalação do Chromium
# O comando oficial da imagem Microsoft já traz os navegadores em /ms-playwright.
# Mas vamos rodar o install apenas para garantir compatibilidade de versão.
RUN playwright install chromium

# Copia o código fonte
COPY main.py .

# Expõe a porta
EXPOSE 8000

# Comando de inicialização
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
