# High-Performance Web Scraper API

API de Web Scraping robusta e assíncrona construída com FastAPI e Playwright, projetada para alta performance, extração de dados em massa e fácil deploy via Docker (Coolify/Portainer).

## Funcionalidades

- **Playwright Async:** Navegação real em headless browser (Chromium).
- **Concorrência Controlada:** Semaphore global para limitar uso de recursos (`MAX_CONCURRENCY`).
- **Rotação de Proxies:** Integração automática com ProxyScrape.
- **Extração Híbrida:** Combina Regex, BeautifulSoup e avaliação de JS para extrair:
  - Emails, Telefones, CNPJ, WhatsApp.
  - Redes Sociais (LinkedIn, Facebook, Instagram, etc.).
  - Pixels de Rastreamento (Facebook, Google Analytics, TikTok).
  - Links de Checkout (Hotmart, Kiwify, etc.).
  - Metadados e Screenshots.
  - Conversão de HTML para Markdown.
- **Otimizações:** Block de mídia/fontes, Smart Scroll para Lazy Loading, Reutilização de Browser Context.

## Como Rodar

### Pré-requisitos

- Docker
- Docker Compose

### Passo a Passo

1.  **Construir e Subir o Container:**

    ```bash
    docker-compose up -d --build
    ```

2.  **Acessar a Documentação (Swagger UI):**

    Abra seu navegador em: `http://localhost:8000/docs`

3.  **Testar a API (Exemplo de Requisição):**

    Endpoint: `POST /scrape`

    ```json
    {
      "url": "https://exemplo.com.br",
      "extract_images": true,
      "take_screenshot": false,
      "timeout": 30000
    }
    ```

## Variáveis de Ambiente

| Variável | Descrição | Padrão |
| :--- | :--- | :--- |
| `MAX_CONCURRENCY` | Número máximo de abas/processos simultâneos. | `5` |
| `PYTHONUNBUFFERED` | Força logs diretos para o stdout. | `1` |

## Deploy (Coolify / Portainer)

### Docker Compose (Recomendado)

Utilize o arquivo `docker-compose.yml` incluído. Ele já configura limites de recursos (CPU/RAM) e Healthchecks essenciais para orquestradores.

### Dockerfile Puro

Se preferir usar apenas o `Dockerfile`:

1.  Selecione a origem (GitHub/GitLab ou Upload).
2.  Defina a porta interna como `8000`.
3.  Adicione a variável de ambiente `MAX_CONCURRENCY` ajustada para a capacidade do seu servidor (ex: 1GB RAM ~= 2-3 Concurrency).

## Estrutura do Projeto

- `main.py`: Aplicação FastAPI e lógica de scraping.
- `Dockerfile`: Configuração da imagem Docker otimizada.
- `requirements.txt`: Dependências Python.
- `docker-compose.yml`: Orquestração local e produção.
