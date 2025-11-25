# Base Image otimizada para Playwright e Python
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# Define diretório de trabalho
WORKDIR /app

# Configurações de ambiente para evitar buffer e definir concorrência padrão
ENV PYTHONUNBUFFERED=1
ENV MAX_CONCURRENCY=5

# Copia e instala dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala apenas o navegador necessário (Chromium) para economizar espaço/tempo
RUN playwright install chromium

# Copia o código fonte
COPY main.py .

# Expõe a porta da API
EXPOSE 8000

# Comando de inicialização
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
