import os
import asyncio
import random
import time
import base64
import re
import logging
import gc
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

import aiohttp
import trafilatura
from fake_useragent import UserAgent
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Error as PlaywrightError
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

# --- Configuração de Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebScraperAPI")

# --- Constants & Configs ---
BLOCKED_RESOURCE_TYPES = ["image", "media", "font", "texttrack", "object", "beacon", "csp_report", "imageset"]
BLOCKED_URL_PATTERNS = [
    "google-analytics.com", 
    "doubleclick.net", 
    "googlesyndication.com", 
    "facebook.net/en_US/fbevents.js",
    "adsystem.com",
    "adservice.google.com",
    "connect.facebook.net"
]
BROWSER_RESTART_LIMIT = 200

# --- ADVANCED STEALTH SCRIPT (State of the Art 2025) ---
# Engana testes de Webdriver, Chrome Runtime, Permissions, Plugins e WebGL.
ADVANCED_STEALTH_JS = """
(() => {
    const newProto = navigator.__proto__;
    delete newProto.webdriver;
    navigator.__proto__ = newProto;

    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    
    // Mock Chrome Object
    if (!window.chrome) {
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
    }

    // Mock Permissions
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
    );

    // Mock Plugins
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });

    // Mock Languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['pt-BR', 'pt', 'en-US', 'en'],
    });

    // WebGL Vendor Spoofing
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        // UNMASKED_VENDOR_WEBGL
        if (parameter === 37445) {
            return 'Intel Inc.';
        }
        // UNMASKED_RENDERER_WEBGL
        if (parameter === 37446) {
            return 'Intel Iris OpenGL Engine';
        }
        return getParameter(parameter);
    };
})();
"""

# --- Modelos Pydantic ---

class ScrapeRequest(BaseModel):
    url: str
    extract_images: bool = False
    take_screenshot: bool = False
    timeout: int = 20000

class SocialMedia(BaseModel):
    linkedin: List[str] = []
    facebook: List[str] = []
    instagram: List[str] = []
    youtube: List[str] = []
    twitter: List[str] = []

class Images(BaseModel):
    logos: List[str] = []
    favicon: str = ""
    other_images: List[str] = []

class Checkouts(BaseModel):
    have_checkouts: bool = False
    platforms: List[str] = []

class PixelDetail(BaseModel):
    facebook: bool = False
    google_analytics: bool = False
    google_ads: bool = False
    tiktok: bool = False
    pinterest: bool = False
    twitter: bool = False
    linkedin: bool = False
    snapchat: bool = False
    taboola: bool = False
    outbrain: bool = False

class Pixels(BaseModel):
    have_pixels: bool = False
    pixels: PixelDetail

class Screenshot(BaseModel):
    base64: str = ""
    timestamp: str = ""

class Performance(BaseModel):
    total_time: str

class ScrapeResponse(BaseModel):
    status: str
    url: str
    method: str = "dynamic"
    emails: List[str] = []
    phones: List[str] = []
    cnpj: List[str] = []
    whatsapp: List[str] = []
    social_media: SocialMedia
    metadata: Dict[str, str] = {}
    images: Images
    button_links: List[str] = []
    checkouts: Checkouts
    pixels: Pixels
    screenshot: Screenshot
    markdown: str = ""
    performance: Performance

# --- Variáveis Globais ---
PLAYWRIGHT_INSTANCE = None
BROWSER: Optional[Browser] = None
SEMAPHORE: Optional[asyncio.Semaphore] = None
ACTIVE_CONNECTIONS = 0
REQUEST_COUNT = 0
UA_GENERATOR = None

# --- Funções Auxiliares ---

async def init_browser():
    """Inicializa ou Reinicializa o Browser."""
    global PLAYWRIGHT_INSTANCE, BROWSER
    logger.info("Iniciando Playwright (Stealth Mode Ready)...")
    if PLAYWRIGHT_INSTANCE is None:
        PLAYWRIGHT_INSTANCE = await async_playwright().start()
    
    if BROWSER:
        await BROWSER.close()
        
    BROWSER = await PLAYWRIGHT_INSTANCE.chromium.launch(
        headless=True,
        args=[
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--disable-setuid-sandbox',
            '--disable-blink-features=AutomationControlled',
            '--disable-infobars',
            '--hide-scrollbars',
            '--mute-audio'
        ]
    )

async def restart_browser_if_needed():
    """Reinicia o browser se atingir o limite de requisições e estiver ocioso."""
    global REQUEST_COUNT, ACTIVE_CONNECTIONS
    if REQUEST_COUNT >= BROWSER_RESTART_LIMIT and ACTIVE_CONNECTIONS == 0:
        logger.info(f"Limite de requisições ({REQUEST_COUNT}) atingido. Reiniciando navegador para limpar memória...")
        try:
            await init_browser()
            REQUEST_COUNT = 0
            gc.collect()
            logger.info("Navegador reiniciado com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao reiniciar navegador: {e}")

async def smart_scroll(page: Page):
    """Rola a página até o fim para carregar conteúdo Lazy Load."""
    try:
        # Scroll suave até o fim
        await page.evaluate("""
            async () => {
                await new Promise((resolve) => {
                    var totalHeight = 0;
                    var distance = 100;
                    var timer = setInterval(() => {
                        var scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance;

                        if(totalHeight >= scrollHeight - window.innerHeight){
                            clearInterval(timer);
                            resolve();
                        }
                    }, 100);
                });
            }
        """)
        try:
            await page.wait_for_load_state("networkidle", timeout=3000)
        except:
            pass 
    except Exception as e:
        logger.warning(f"Erro no Smart Scroll: {e}")

def extract_regex(text: str) -> Dict[str, List[str]]:
    """Extrai e-mails, telefones e CNPJ usando Regex."""
    emails = list(set(re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)))
    phones = list(set(re.findall(r"\(?\d{2}\)?\s?\d{4,5}-?\d{4}", text)))
    cnpjs = list(set(re.findall(r"\d{2}\.\d{3}\.\d{3}\/\d{4}-\d{2}", text)))
    return {"emails": emails, "phones": phones, "cnpj": cnpjs}

def get_checkouts(soup: BeautifulSoup, text_content: str) -> Checkouts:
    platforms_detected = set()
    
    # Keywords in URLs (Advanced List 2025)
    checkout_keywords = {
        "hotmart": ["pay.hotmart.com", "hotmart.com/checkout"],
        "kiwify": ["pay.kiwify.com.br", "kiwify.app"],
        "eduzz": ["sun.eduzz.com", "chk.eduzz.com"],
        "monetizze": ["app.monetizze.com.br/checkout"],
        "braip": ["ev.braip.com/checkout", "pay.braip.com"],
        "ticto": ["checkout.ticto.com.br"],
        "kirvano": ["pay.kirvano.com"],
        "stripe": ["checkout.stripe.com", "js.stripe.com"],
        "paypal": ["paypal.com/cgi-bin/webscr", "paypal.com/checkout"],
        "shopify": ["myshopify.com", "cdn.shopify.com"],
        "woocommerce": ["/checkout/", "wc-ajax="],
        "yampi": ["seguro.yampi.com.br", "yampi.io"],
        "cartpanda": ["cartpanda.com", "mycartpanda.com"],
        "cloudfox": ["pay.cloudfox.net"]
    }
    
    # 1. Verifica links href
    for a in soup.find_all("a", href=True):
        href = a['href'].lower()
        for platform, patterns in checkout_keywords.items():
            for pattern in patterns:
                if pattern in href:
                    platforms_detected.add(platform)
                    break
    
    # 2. Verifica Scripts (src)
    for script in soup.find_all("script", src=True):
        src = script['src'].lower()
        if "hotmart" in src: platforms_detected.add("hotmart")
        if "eduzz" in src: platforms_detected.add("eduzz")
        if "stripe.com" in src: platforms_detected.add("stripe")
        if "paypal.com" in src: platforms_detected.add("paypal")
        if "shopify" in src: platforms_detected.add("shopify")
        if "woocommerce" in src: platforms_detected.add("woocommerce")
        if "yampi" in src: platforms_detected.add("yampi")

    return Checkouts(have_checkouts=len(platforms_detected) > 0, platforms=list(platforms_detected))

def detect_pixels_html(html_content: str) -> Pixels:
    """Fallback: Detecta pixels analisando o HTML bruto (Regex), útil se o JS for bloqueado."""
    pixels = PixelDetail()
    
    # Facebook: fbq('init', '123...')
    if re.search(r"fbq\s*\(\s*['\"]init['\"]\s*,\s*['\"](\d+)['\"]", html_content):
        pixels.facebook = True
        
    # Google Analytics: UA-XXXX or G-XXXX
    if re.search(r"['\"](UA-\d+-\d+|G-[A-Z0-9]+)['\"]", html_content):
        pixels.google_analytics = True
        
    # Google Ads: AW-XXXX
    if re.search(r"['\"]AW-\d+['\"]", html_content):
        pixels.google_ads = True
        
    # TikTok: ttq.load('XXXX')
    if re.search(r"ttq\.load\s*\(\s*['\"]([A-Z0-9]+)['\"]", html_content):
        pixels.tiktok = True
        
    # Pinterest: pintrk('load', 'XXXX')
    if re.search(r"pintrk\s*\(\s*['\"]load['\"]\s*,\s*['\"](\d+)['\"]", html_content):
        pixels.pinterest = True
    
    # Twitter: twq('init', 'XXXX')
    if re.search(r"twq\s*\(\s*['\"]init['\"]\s*,\s*['\"]([a-zA-Z0-9]+)['\"]", html_content):
        pixels.twitter = True
        
    # LinkedIn: _linkedin_partner_id = "XXXX"
    if re.search(r"_linkedin_partner_id\s*=\s*['\"](\d+)['\"]", html_content):
        pixels.linkedin = True
        
    # Snapchat: snaptr('init', 'XXXX')
    if re.search(r"snaptr\s*\(\s*['\"]init['\"]\s*,\s*['\"]([a-zA-Z0-9-]+)['\"]", html_content):
        pixels.snapchat = True
        
    # Taboola: _tfa.push({notify: 'event', name: 'page_view', id: 123})
    if "trc.taboola.com" in html_content:
        pixels.taboola = True
        
    # Outbrain: obApi('track', ...)
    if "widgets.outbrain.com/outbrain.js" in html_content:
        pixels.outbrain = True

    has_pixels = any(dict(pixels).values())
    return Pixels(have_pixels=has_pixels, pixels=pixels)

async def detect_pixels_js(page: Page) -> Pixels:
    # ... (JS detection logic remains same)
    try:
        result = await page.evaluate("""() => {
            return {
                facebook: !!(window.fbq || window._fbq),
                google_analytics: !!(window.ga || window.gtag || window.GoogleAnalyticsObject),
                google_ads: !!(window.ads_gtag || (window.gtag && JSON.stringify(window.dataLayer || []).includes('AW-'))),
                tiktok: !!(window.ttq),
                pinterest: !!(window.pintrk),
                twitter: !!(window.twq),
                linkedin: !!(window._linkedin_data_partner_ids),
                snapchat: !!(window.snaptr),
                taboola: !!(window._tfa),
                outbrain: !!(window.obApi)
            }
        }""")
        return Pixels(have_pixels=any(result.values()), pixels=PixelDetail(**result))
    except Exception:
        return Pixels(have_pixels=False, pixels=PixelDetail())

def clean_and_deduplicate(items: List[str]) -> List[str]:
    """Remove duplicatas e limpa URLs/Strings similares."""
    if not items:
        return []
    
    unique_items = {}
    for item in items:
        # Normalização para chave de comparação
        if item.startswith("http"):
            # Remove query params para comparar a URL base
            key = item.split("?")[0].rstrip("/")
        else:
            # Remove espaços e caracteres não alfanuméricos para comparar telefones/textos
            key = re.sub(r'\W+', '', item).lower()
        
        # Lógica de preferência: Mantém a URL mais curta se houver conflito de chaves (menos lixo)
        if key not in unique_items:
            unique_items[key] = item
        else:
            if len(item) < len(unique_items[key]):
                unique_items[key] = item
                
    return list(unique_items.values())

# --- Lógica de Scraping com Retry ---

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(Exception), reraise=True)
async def execute_scraping_task(request: ScrapeRequest) -> ScrapeResponse:
    global BROWSER, PROXY_LIST, UA_GENERATOR
    
    context: Optional[BrowserContext] = None
    page: Optional[Page] = None
    start_time = time.perf_counter()

    try:
        # Proxy Configuration: ALWAYS NONE (no proxy functionality)
        proxy_config = None
            
        logger.info(f"Iniciando navegação para {request.url} | Proxy Config: NULO (funcionalidade removida)")

        # User Agent Rotativo e Realista
        try:
            user_agent = UA_GENERATOR.random
        except:
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        
        try:
            context = await BROWSER.new_context(
                user_agent=user_agent,
                proxy=proxy_config, # Sempre None agora
                viewport={"width": 1280 + random.randint(0, 100), "height": 720 + random.randint(0, 100)}, # Viewport randomizado
                locale="pt-BR",
                timezone_id="America/Sao_Paulo"
            )
        except Exception as e:
            logger.warning(f"Falha ao criar contexto, usando configuração padrão: {e}")
            context = await BROWSER.new_context(user_agent=user_agent)

        # --- INJEÇÃO DE STEALTH AVANÇADO ---
        await context.add_init_script(ADVANCED_STEALTH_JS)

        page = await context.new_page()

        # --- BLOQUEIO AGRESSIVO DE RECURSOS ---
        async def route_handler(route):
            req_url = route.request.url.lower()
            resource_type = route.request.resource_type

            if resource_type in BLOCKED_RESOURCE_TYPES:
                await route.abort()
                return
            
            if not request.take_screenshot and resource_type == "stylesheet":
                await route.abort()
                return

            if any(pattern in req_url for pattern in BLOCKED_URL_PATTERNS):
                await route.abort()
                return

            await route.continue_()

        await page.route("**/*", route_handler)

        # Navegação
        await page.goto(request.url, timeout=request.timeout, wait_until="domcontentloaded")
        await smart_scroll(page)

        # Extração
        content_html = await page.content()
        soup = BeautifulSoup(content_html, 'lxml')
        
        try:
            body_text = await page.evaluate("document.body.innerText")
        except:
            body_text = soup.get_text(separator="\n")

        regex_data = extract_regex(body_text)
        
        # Metadados
        title = await page.title()
        desc_tag = soup.find("meta", attrs={"name": "description"})
        description = desc_tag["content"] if desc_tag else ""
        og_image_tag = soup.find("meta", property="og:image")
        og_image = og_image_tag["content"] if og_image_tag else ""

        # Redes Sociais & Links
        social_links = {"linkedin": [], "facebook": [], "instagram": [], "youtube": [], "twitter": []}
        whatsapp_links = []
        whatsapp_seen_numbers = set() # Para evitar duplicatas de números
        button_links = []

        for a in soup.find_all("a", href=True):
            href = a['href'].lower()
            original_href = a['href'] # Mantém case original para o link final
            txt = a.get_text(strip=True)
            
            if "linkedin.com" in href: social_links["linkedin"].append(href)
            elif "facebook.com" in href: social_links["facebook"].append(href)
            elif "instagram.com" in href: social_links["instagram"].append(href)
            elif "youtube.com" in href: social_links["youtube"].append(href)
            elif "twitter.com" in href or "x.com" in href: social_links["twitter"].append(href)
            
            # Lógica otimizada para WhatsApp
            if "wa.me" in href or "api.whatsapp.com" in href or "web.whatsapp.com" in href:
                # Tenta extrair o número para usar como chave única
                phone_match = re.search(r'phone=(\d+)', original_href) or re.search(r'wa\.me/(\d+)', original_href)
                
                if phone_match:
                    number = phone_match.group(1)
                    if number not in whatsapp_seen_numbers:
                        whatsapp_seen_numbers.add(number)
                        whatsapp_links.append(original_href)
                else:
                    # Se não achar número (link genérico), adiciona se a URL exata não existir
                    if original_href not in whatsapp_links:
                        whatsapp_links.append(original_href)

            if txt: button_links.append(original_href)

        # Imagens
        images_data = Images()
        if request.extract_images:
            imgs = [img['src'] for img in soup.find_all('img', src=True)]
            images_data.other_images = clean_and_deduplicate(imgs)[:10] # Limpeza aqui
            icon_link = soup.find("link", rel="icon") or soup.find("link", rel="shortcut icon")
            if icon_link and icon_link.get("href"):
                images_data.favicon = icon_link["href"]

        # Pixels (Híbrido: JS + HTML Regex)
        pixels_js = await detect_pixels_js(page)
        pixels_html = detect_pixels_html(content_html)
        
        # Merge dos resultados (OR bit a bit lógico)
        merged_pixels = PixelDetail(
            facebook=pixels_js.pixels.facebook or pixels_html.pixels.facebook,
            google_analytics=pixels_js.pixels.google_analytics or pixels_html.pixels.google_analytics,
            google_ads=pixels_js.pixels.google_ads or pixels_html.pixels.google_ads,
            tiktok=pixels_js.pixels.tiktok or pixels_html.pixels.tiktok,
            pinterest=pixels_js.pixels.pinterest or pixels_html.pixels.pinterest,
            twitter=pixels_js.pixels.twitter or pixels_html.pixels.twitter,
            linkedin=pixels_js.pixels.linkedin or pixels_html.pixels.linkedin,
            snapchat=pixels_js.pixels.snapchat or pixels_html.pixels.snapchat,
            taboola=pixels_js.pixels.taboola or pixels_html.pixels.taboola,
            outbrain=pixels_js.pixels.outbrain or pixels_html.pixels.outbrain
        )
        
        pixels_data = Pixels(
            have_pixels=pixels_js.have_pixels or pixels_html.have_pixels,
            pixels=merged_pixels
        )

        checkouts_data = get_checkouts(soup, body_text)

        # Screenshot
        screenshot_data = Screenshot()
        if request.take_screenshot:
            b64 = await page.screenshot(full_page=False, type='jpeg', quality=70)
            screenshot_data.base64 = base64.b64encode(b64).decode("utf-8")
            screenshot_data.timestamp = str(time.time())

        # --- EXTRAÇÃO DE MARKDOWN COM TRAFILATURA (State of the Art) ---
        try:
            markdown_content = trafilatura.extract(content_html, output_format='markdown', include_links=True, include_images=request.extract_images)
            if not markdown_content:
                 # Fallback simples se Trafilatura não achar "artigo"
                 markdown_content = soup.get_text(separator="\n")
        except Exception:
            markdown_content = soup.get_text(separator="\n")

        end_time = time.perf_counter()
        total_time = f"{end_time - start_time:.2f}s"

        # --- LIMPEZA FINAL DE DUPLICATAS ---
        final_emails = clean_and_deduplicate(regex_data["emails"])
        final_phones = clean_and_deduplicate(regex_data["phones"])
        final_cnpj = clean_and_deduplicate(regex_data["cnpj"])
        final_whatsapp = clean_and_deduplicate(whatsapp_links)
        final_buttons = clean_and_deduplicate(button_links)[:20]
        
        final_social = {}
        for k, v in social_links.items():
            final_social[k] = clean_and_deduplicate(v)

        return ScrapeResponse(
            status="success",
            url=request.url,
            emails=final_emails,
            phones=final_phones,
            cnpj=final_cnpj,
            whatsapp=final_whatsapp,
            social_media=SocialMedia(**final_social),
            metadata={"title": title, "description": description, "og_image": og_image},
            images=images_data,
            button_links=final_buttons,
            checkouts=checkouts_data,
            pixels=pixels_data,
            screenshot=screenshot_data,
            markdown=markdown_content[:20000],
            performance=Performance(total_time=total_time)
        )

    finally:
        if page: await page.close()
        if context: await context.close()

# --- Ciclo de Vida da Aplicação ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    global PLAYWRIGHT_INSTANCE, BROWSER, SEMAPHORE, UA_GENERATOR
    
    max_concurrency = int(os.getenv("MAX_CONCURRENCY", 5))
    SEMAPHORE = asyncio.Semaphore(max_concurrency)
    logger.info(f"Semaphore inicializado com {max_concurrency} slots.")
    
    # Inicializa Fake UserAgent com cache
    try:
        UA_GENERATOR = UserAgent(browsers=['chrome', 'edge', 'firefox'], os=['windows', 'macos'])
    except:
        UA_GENERATOR = None
        logger.warning("Fake UserAgent falhou, usando fallback.")

    await init_browser()
    
    yield
    
    logger.info("Fechando Browser e Playwright...")
    if BROWSER: await BROWSER.close()
    if PLAYWRIGHT_INSTANCE: await PLAYWRIGHT_INSTANCE.stop()

app = FastAPI(lifespan=lifespan, title="High-Performance Scraper API (Enhanced 2025 - No Proxies)")

# --- Endpoints ---

@app.get("/health")
async def health_check():
    return {
        "status": "online",
        "active_connections": ACTIVE_CONNECTIONS,
        "request_count_since_restart": REQUEST_COUNT,
        "proxy_functionality": "REMOVIDA",
        "ram_available_system": "Check via Docker Stats"
    }

@app.post("/scrape", response_model=ScrapeResponse)
async def scrape(request: ScrapeRequest):
    global ACTIVE_CONNECTIONS, REQUEST_COUNT
    
    if not SEMAPHORE:
        raise HTTPException(status_code=500, detail="Sistema inicializando.")

    ACTIVE_CONNECTIONS += 1
    async with SEMAPHORE:
        try:
            result = await execute_scraping_task(request)
            return result
        except Exception as e:
            logger.error(f"Erro Fatal após retentativas {request.url}: {str(e)}")
            return ScrapeResponse(
                status="error",
                url=request.url,
                social_media=SocialMedia(),
                images=Images(),
                checkouts=Checkouts(),
                pixels=Pixels(pixels=PixelDetail()),
                screenshot=Screenshot(),
                performance=Performance(total_time="0s"),
                markdown=f"Error after retries: {str(e)}"
            )
        finally:
            ACTIVE_CONNECTIONS -= 1
            REQUEST_COUNT += 1
            gc.collect()
            await restart_browser_if_needed()