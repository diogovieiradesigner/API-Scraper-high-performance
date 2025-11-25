# Base Image otimizada para Playwright e Python
FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

# Define diretório de trabalho
WORKDIR /app

# Configurações de ambiente
ENV PYTHONUNBUFFERED=1
ENV MAX_CONCURRENCY=5
# Garante que o Playwright saiba onde procurar os browsers
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Copia e instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala o navegador Chromium e dependências do sistema
# --with-deps garante que libs do Linux necessárias sejam instaladas
RUN playwright install chromium --with-deps

# Copia o código fonte (respeitando o .dockerignore)
COPY main.py .

# Expõe a porta da API
EXPOSE 8000

# Comando de inicialização
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]